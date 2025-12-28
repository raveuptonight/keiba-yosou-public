#!/usr/bin/env python3
"""
機械学習モデル学習スクリプト

JRA-VANデータから特徴量を抽出し、XGBoostモデルを学習する
差分チェック機能付き
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.features.feature_pipeline import FeatureExtractor
from src.models.xgboost_model import HorseRacingXGBoost
from src.db.connection import get_db

# ロガー設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ディレクトリ設定
MODEL_DIR = Path("/app/models") if Path("/app/models").exists() else project_root / "models"
DATA_DIR = Path("/app/data") if Path("/app/data").exists() else project_root / "data"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 差分チェック用ファイル
LAST_TRAIN_STATE_FILE = DATA_DIR / "last_train_state.json"


def get_db_state() -> dict:
    """
    現在のDBの状態を取得（差分チェック用）

    Returns:
        {
            "total_races": int,
            "latest_race_id": str,
            "latest_race_date": str
        }
    """
    db = get_db()
    conn = db.get_connection()

    if not conn:
        logger.error("DB接続失敗")
        return {}

    try:
        cursor = conn.cursor()

        # 総レース数と最新レースを取得
        cursor.execute("""
            SELECT
                COUNT(DISTINCT race_id) as total_races,
                MAX(race_id) as latest_race_id
            FROM uma_race
            WHERE kakutei_chakujun IS NOT NULL
        """)

        row = cursor.fetchone()

        state = {
            "total_races": row[0] if row else 0,
            "latest_race_id": row[1] if row else "",
            "checked_at": datetime.now().isoformat()
        }

        logger.info(f"DB状態: total_races={state['total_races']}, latest_race_id={state['latest_race_id']}")
        return state

    except Exception as e:
        logger.error(f"DB状態取得エラー: {e}")
        return {}

    finally:
        cursor.close()
        conn.close()


def load_last_train_state() -> dict:
    """
    前回の学習状態を読み込み

    Returns:
        前回の状態（なければ空dict）
    """
    if not LAST_TRAIN_STATE_FILE.exists():
        logger.info("前回の学習状態ファイルなし（初回実行）")
        return {}

    try:
        with open(LAST_TRAIN_STATE_FILE, 'r') as f:
            state = json.load(f)
            logger.info(f"前回の学習状態: {state}")
            return state
    except Exception as e:
        logger.warning(f"前回の学習状態読み込みエラー: {e}")
        return {}


def save_train_state(state: dict) -> None:
    """
    学習状態を保存

    Args:
        state: 保存する状態
    """
    state["trained_at"] = datetime.now().isoformat()

    try:
        with open(LAST_TRAIN_STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        logger.info(f"学習状態保存完了: {LAST_TRAIN_STATE_FILE}")
    except Exception as e:
        logger.error(f"学習状態保存エラー: {e}")


def check_need_training() -> tuple[bool, dict]:
    """
    学習が必要かチェック

    Returns:
        (need_training: bool, current_state: dict)
    """
    current_state = get_db_state()

    if not current_state:
        logger.warning("DB状態取得失敗、学習スキップ")
        return False, {}

    last_state = load_last_train_state()

    if not last_state:
        logger.info("初回学習")
        return True, current_state

    # 差分チェック
    last_total = last_state.get("total_races", 0)
    current_total = current_state.get("total_races", 0)

    last_latest = last_state.get("latest_race_id", "")
    current_latest = current_state.get("latest_race_id", "")

    new_races = current_total - last_total

    if new_races > 0:
        logger.info(f"新規レース検出: +{new_races}件 (前回: {last_total} → 今回: {current_total})")
        return True, current_state

    if current_latest != last_latest:
        logger.info(f"最新レースID変更: {last_latest} → {current_latest}")
        return True, current_state

    logger.info("差分なし、学習スキップ")
    return False, current_state


def fetch_training_data(limit: int = None) -> pd.DataFrame:
    """
    学習用データをDBから取得

    Args:
        limit: 取得レース数の上限（None=全件）

    Returns:
        DataFrame: 学習データ
    """
    logger.info("学習データ取得開始...")

    db = get_db()
    conn = db.get_connection()

    if not conn:
        logger.error("DB接続失敗")
        return pd.DataFrame()

    try:
        cursor = conn.cursor()

        # 過去レース結果を取得（確定データのみ）
        query = """
            SELECT
                race_id,
                umaban,
                kakutei_chakujun as finish_position
            FROM uma_race
            WHERE kakutei_chakujun IS NOT NULL
                AND kakutei_chakujun > 0
            ORDER BY race_id DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)
        rows = cursor.fetchall()

        df = pd.DataFrame(rows, columns=['race_id', 'umaban', 'finish_position'])
        logger.info(f"取得レコード数: {len(df)}")

        return df

    except Exception as e:
        logger.error(f"データ取得エラー: {e}")
        return pd.DataFrame()

    finally:
        cursor.close()
        conn.close()


def extract_features_for_training(race_data: pd.DataFrame) -> tuple:
    """
    学習データから特徴量を抽出

    Args:
        race_data: レース結果データ

    Returns:
        (X, y): 特徴量と目的変数
    """
    logger.info("特徴量抽出開始...")

    extractor = FeatureExtractor()

    all_features = []
    all_labels = []

    # レースごとに処理
    race_ids = race_data['race_id'].unique()
    total = len(race_ids)

    for i, race_id in enumerate(race_ids):
        if i % 1000 == 0:
            logger.info(f"進捗: {i}/{total} ({i/total*100:.1f}%)")

        race_horses = race_data[race_data['race_id'] == race_id]

        for _, row in race_horses.iterrows():
            try:
                features = extractor.extract_features(race_id, row['umaban'])
                all_features.append(features)
                all_labels.append(row['finish_position'])
            except Exception as e:
                logger.warning(f"特徴量抽出失敗: race_id={race_id}, umaban={row['umaban']}, error={e}")
                continue

    X = pd.DataFrame(all_features)
    y = pd.Series(all_labels)

    logger.info(f"特徴量抽出完了: samples={len(X)}, features={len(X.columns)}")

    return X, y


def train_model(X: pd.DataFrame, y: pd.Series) -> HorseRacingXGBoost:
    """
    モデルを学習

    Args:
        X: 特徴量
        y: 目的変数（着順）

    Returns:
        学習済みモデル
    """
    logger.info("モデル学習開始...")

    model = HorseRacingXGBoost()
    metrics = model.train(X, y)

    logger.info(f"学習完了: RMSE={metrics['rmse']:.4f}, MAE={metrics['mae']:.4f}")

    return model


def save_model(model: HorseRacingXGBoost) -> str:
    """
    モデルを保存

    Args:
        model: 学習済みモデル

    Returns:
        保存先パス
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = MODEL_DIR / f"xgboost_model_{timestamp}.pkl"

    model.save(str(filepath))

    # latest シンボリックリンクを更新
    latest_path = MODEL_DIR / "xgboost_model_latest.pkl"
    if latest_path.exists() or latest_path.is_symlink():
        latest_path.unlink()
    latest_path.symlink_to(filepath.name)

    logger.info(f"モデル保存完了: {filepath}")
    logger.info(f"シンボリックリンク更新: {latest_path}")

    return str(filepath)


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(description="競馬予想モデル学習")
    parser.add_argument("--check-diff", action="store_true", help="差分チェックして新規データがある場合のみ学習")
    parser.add_argument("--force", action="store_true", help="強制的に学習を実行")
    parser.add_argument("--limit", type=int, default=50000, help="学習データの上限件数")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("競馬予想モデル学習スクリプト")
    logger.info(f"オプション: check-diff={args.check_diff}, force={args.force}, limit={args.limit}")
    logger.info("=" * 60)

    try:
        # 差分チェック
        if args.check_diff and not args.force:
            need_training, current_state = check_need_training()

            if not need_training:
                logger.info("新規データなし、学習をスキップします")
                logger.info("=" * 60)
                return

        # 1. データ取得
        race_data = fetch_training_data(limit=args.limit)

        if race_data.empty:
            logger.error("学習データが取得できませんでした")
            sys.exit(1)

        # 2. 特徴量抽出
        X, y = extract_features_for_training(race_data)

        if X.empty:
            logger.error("特徴量が抽出できませんでした")
            sys.exit(1)

        # 3. モデル学習
        model = train_model(X, y)

        # 4. モデル保存
        filepath = save_model(model)

        # 5. 学習状態を保存
        if args.check_diff:
            save_train_state(current_state)

        # 6. 特徴量重要度を表示
        importance = model.get_feature_importance()
        logger.info("特徴量重要度 TOP10:")
        for i, (name, score) in enumerate(list(importance.items())[:10], 1):
            logger.info(f"  {i}. {name}: {score:.4f}")

        logger.info("=" * 60)
        logger.info("学習完了!")
        logger.info(f"モデル保存先: {filepath}")
        logger.info("=" * 60)

    except Exception as e:
        logger.exception(f"学習処理でエラー発生: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
