"""
予想サービス

レース予想の生成、保存、取得を管理するサービスレイヤー
"""

import logging
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path
import asyncpg
import numpy as np

import os

# MLモデルパス（ensemble_modelのみ使用）
ML_MODEL_PATH = Path("/app/models/ensemble_model_latest.pkl")
if not ML_MODEL_PATH.exists():
    # ローカル開発時のパス
    ML_MODEL_PATH = Path(__file__).parent.parent.parent / "models" / "ensemble_model_latest.pkl"

from src.api.schemas.prediction import (
    PredictionResponse,
    PredictionResult,
    HorseRankingEntry,
    PositionDistribution,
    PredictionHistoryItem,
)
from src.exceptions import (
    PredictionError,
    DatabaseQueryError,
    MissingDataError,
)
from src.db.table_names import (
    COL_RACE_ID,
    COL_RACE_NAME,
    COL_JYOCD,
    COL_KAISAI_YEAR,
    COL_KAISAI_MONTHDAY,
)

logger = logging.getLogger(__name__)

# バイアスデータのキャッシュ
_bias_cache = {}


def _load_bias_for_date(target_date: str) -> Optional[Dict]:
    """
    指定日のバイアスデータをDBから読み込む

    Args:
        target_date: YYYY-MM-DD形式の日付

    Returns:
        バイアスデータ辞書、または None
    """
    from datetime import datetime
    from src.features.daily_bias import DailyBiasAnalyzer

    if target_date in _bias_cache:
        return _bias_cache[target_date]

    try:
        # 日付をdateオブジェクトに変換
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()

        # DBからバイアスを読み込み
        analyzer = DailyBiasAnalyzer()
        bias_result = analyzer.load_bias(date_obj)

        if bias_result:
            data = bias_result.to_dict()
            _bias_cache[target_date] = data
            logger.info(f"バイアスデータをDBから読み込み: {target_date}")
            return data

    except Exception as e:
        logger.error(f"バイアスデータ読み込みエラー: {e}")

    return None


def _apply_bias_to_scores(
    ml_scores: Dict[str, Any],
    race_id: str,
    horses: List[Dict],
    bias_data: Dict
) -> Dict[str, Any]:
    """
    MLスコアにバイアス調整を適用

    Args:
        ml_scores: 元のMLスコア {馬番: {rank_score, win_probability}}
        race_id: レースID
        horses: 出走馬情報リスト
        bias_data: バイアスデータ

    Returns:
        調整後のスコア
    """
    venue_code = race_id[8:10]  # レースIDの9-10桁目が競馬場コード（年4+月2+回2+場2）

    venue_biases = bias_data.get('venue_biases', {})
    jockey_performances = bias_data.get('jockey_performances', {})

    if venue_code not in venue_biases:
        logger.info(f"競馬場バイアスなし: venue_code={venue_code}")
        return ml_scores

    vb = venue_biases[venue_code]
    waku_bias = vb.get('waku_bias', 0)
    pace_bias = vb.get('pace_bias', 0)

    logger.info(f"バイアス適用: {vb.get('venue_name', venue_code)}, "
                f"枠={waku_bias:.3f}, ペース={pace_bias:.3f}")

    adjusted_scores = {}

    for umaban_str, score_data in ml_scores.items():
        try:
            umaban = int(umaban_str)
        except ValueError:
            adjusted_scores[umaban_str] = score_data
            continue

        # 馬情報を検索
        horse_info = None
        for h in horses:
            h_umaban = h.get('umaban', '')
            try:
                if int(h_umaban) == umaban:
                    horse_info = h
                    break
            except (ValueError, TypeError):
                pass

        # 調整係数計算
        adjustment = 0.0

        # 1. 枠順バイアス
        if horse_info:
            wakuban = horse_info.get('wakuban', '')
            try:
                waku = int(wakuban)
                if 1 <= waku <= 4:
                    # 内枠: 内枠有利なら加点
                    adjustment += waku_bias * 0.02
                elif 5 <= waku <= 8:
                    # 外枠: 外枠有利（=内枠不利）なら加点
                    adjustment -= waku_bias * 0.02
            except (ValueError, TypeError):
                pass

        # 2. 騎手当日成績バイアス
        if horse_info:
            kishu_code = horse_info.get('kishu_code', '')
            if kishu_code and kishu_code in jockey_performances:
                jp = jockey_performances[kishu_code]
                jockey_win_rate = jp.get('win_rate', 0)
                jockey_top3_rate = jp.get('top3_rate', 0)

                # 当日好調な騎手は加点
                adjustment += jockey_win_rate * 0.03
                adjustment += jockey_top3_rate * 0.01

        # スコア調整（rank_scoreは低いほど良い）
        new_rank_score = score_data.get('rank_score', 999) - adjustment

        # 確率調整（adjustmentが正なら確率上昇）
        old_prob = score_data.get('win_probability', 0)
        new_prob = old_prob * (1 + adjustment * 2)
        new_prob = max(0.001, min(0.99, new_prob))  # 範囲制限

        adjusted_scores[umaban_str] = {
            'rank_score': new_rank_score,
            'win_probability': new_prob,
            'bias_adjustment': adjustment,
        }

    # 確率の正規化
    total_prob = sum(s.get('win_probability', 0) for s in adjusted_scores.values())
    if total_prob > 0:
        for umaban_str in adjusted_scores:
            adjusted_scores[umaban_str]['win_probability'] /= total_prob

    return adjusted_scores


# 競馬場コードマッピング
VENUE_CODE_MAP = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟",
    "05": "東京", "06": "中山", "07": "中京", "08": "京都",
    "09": "阪神", "10": "小倉"
}

# 馬場状態コードマッピング
BABA_CONDITION_MAP = {
    "1": "良", "2": "稍重", "3": "重", "4": "不良"
}

# 天候コードマッピング
WEATHER_CODE_MAP = {
    "1": "晴", "2": "曇", "3": "雨", "4": "小雨", "5": "雪", "6": "小雪"
}


def _get_current_track_condition(conn, race_id: str) -> Optional[Dict]:
    """
    レースの現在の馬場状態・天候を取得

    Args:
        conn: DB接続
        race_id: レースID

    Returns:
        {'track_type': 'shiba'|'dirt', 'condition': 1-4, 'condition_name': '良',
         'weather': 1-6, 'weather_name': '晴'}
    """
    cur = conn.cursor()
    try:
        # 1. レースのトラック種別を取得
        cur.execute('''
            SELECT track_code
            FROM race_shosai
            WHERE race_code = %s
              AND data_kubun IN ('1', '2', '3', '4', '5', '6')
            LIMIT 1
        ''', (race_id,))
        row = cur.fetchone()
        if not row:
            return None

        track_code = row[0] or ''
        # track_code: 10-19=芝, 20-29=ダート
        if track_code.startswith('1'):
            track_type = 'shiba'
        elif track_code.startswith('2'):
            track_type = 'dirt'
        else:
            track_type = 'shiba'  # デフォルト

        # 2. 現在の馬場状態・天候を取得
        # race_id形式: YYYYMMDD(8) + keibajo(2) + kai(2) + nichime(2) + race(2) = 16桁
        # tenko_baba_jotai.race_code形式: YYYYMMDD(8) + keibajo(2) + kai(2) + nichime(2) = 14桁
        # 例: 2026010506010201 → 20260105060102
        baba_race_code = race_id[:14]  # 最後の2桁（レース番号）を除去

        cur.execute('''
            SELECT
                tenko_jotai_genzai,
                baba_jotai_shiba_genzai,
                baba_jotai_dirt_genzai
            FROM tenko_baba_jotai
            WHERE race_code = %s
            ORDER BY insert_timestamp DESC
            LIMIT 1
        ''', (baba_race_code,))
        baba_row = cur.fetchone()

        if not baba_row:
            logger.debug(f"馬場状態データなし: race_id={race_id}")
            return None

        weather_code = baba_row[0] or '0'
        shiba_condition = baba_row[1] or '0'
        dirt_condition = baba_row[2] or '0'

        condition_code = shiba_condition if track_type == 'shiba' else dirt_condition

        result = {
            'track_type': track_type,
            'condition': int(condition_code) if condition_code.isdigit() else 0,
            'condition_name': BABA_CONDITION_MAP.get(condition_code, '不明'),
            'weather': int(weather_code) if weather_code.isdigit() else 0,
            'weather_name': WEATHER_CODE_MAP.get(weather_code, '不明'),
        }

        logger.info(f"馬場状態取得: {result['track_type']}・{result['condition_name']}, 天候: {result['weather_name']}")
        return result

    except Exception as e:
        logger.error(f"馬場状態取得エラー: {e}")
        return None
    finally:
        cur.close()


def _get_horse_baba_performance(conn, kettonums: List[str], track_type: str, condition: int) -> Dict[str, Dict]:
    """
    各馬の馬場状態別成績を取得

    Args:
        conn: DB接続
        kettonums: 血統登録番号リスト
        track_type: 'shiba' or 'dirt'
        condition: 1=良, 2=稍重, 3=重, 4=不良

    Returns:
        {kettonum: {'runs': N, 'wins': N, 'top3': N, 'win_rate': 0.xx, 'top3_rate': 0.xx}}
    """
    if not kettonums or condition == 0:
        return {}

    # カラム名マッピング
    condition_map = {
        1: 'ryo',       # 良
        2: 'yayaomo',   # 稍重
        3: 'omo',       # 重
        4: 'furyo',     # 不良
    }
    condition_suffix = condition_map.get(condition, 'ryo')
    prefix = f"{track_type}_{condition_suffix}"  # e.g., 'shiba_ryo', 'dirt_omo'

    cur = conn.cursor()
    try:
        # shussobetsu_babaテーブルから成績を取得
        placeholders = ','.join(['%s'] * len(kettonums))
        cur.execute(f'''
            SELECT
                ketto_toroku_bango,
                {prefix}_1chaku,
                {prefix}_2chaku,
                {prefix}_3chaku,
                {prefix}_4chaku,
                {prefix}_5chaku,
                {prefix}_chakugai
            FROM shussobetsu_baba
            WHERE ketto_toroku_bango IN ({placeholders})
              AND data_kubun IN ('1', '2', '3', '4', '5', '6')
        ''', kettonums)

        results = {}
        for row in cur.fetchall():
            kettonum = row[0]
            wins = int(row[1] or 0)
            sec = int(row[2] or 0)
            third = int(row[3] or 0)
            fourth = int(row[4] or 0)
            fifth = int(row[5] or 0)
            out = int(row[6] or 0)

            runs = wins + sec + third + fourth + fifth + out
            top3 = wins + sec + third

            if runs > 0:
                results[kettonum] = {
                    'runs': runs,
                    'wins': wins,
                    'top3': top3,
                    'win_rate': wins / runs,
                    'top3_rate': top3 / runs,
                }

        logger.info(f"馬場別成績取得: {len(results)}/{len(kettonums)}頭 ({prefix})")
        return results

    except Exception as e:
        logger.error(f"馬場別成績取得エラー: {e}")
        return {}
    finally:
        cur.close()


def _apply_track_condition_adjustment(
    ml_scores: Dict[str, Any],
    horses: List[Dict],
    track_condition: Dict,
    baba_performance: Dict[str, Dict]
) -> Dict[str, Any]:
    """
    馬場状態に基づいてスコアを調整

    Args:
        ml_scores: 元のMLスコア
        horses: 出走馬情報リスト
        track_condition: 現在の馬場状態
        baba_performance: 各馬の馬場別成績

    Returns:
        調整後のスコア
    """
    if not track_condition or not baba_performance:
        return ml_scores

    condition = track_condition.get('condition', 1)
    condition_name = track_condition.get('condition_name', '良')

    adjusted_scores = {}

    for umaban_str, score_data in ml_scores.items():
        adjustment = 0.0

        # 馬情報を取得
        horse_info = None
        for h in horses:
            if str(h.get('umaban', '')).zfill(2) == umaban_str.zfill(2):
                horse_info = h
                break

        if horse_info:
            kettonum = horse_info.get('ketto_toroku_bango', '')
            if kettonum in baba_performance:
                perf = baba_performance[kettonum]
                runs = perf.get('runs', 0)
                win_rate = perf.get('win_rate', 0)
                top3_rate = perf.get('top3_rate', 0)

                # 経験がある馬のみ調整
                if runs >= 2:
                    # 良馬場以外での実績を評価
                    if condition >= 2:  # 稍重以上
                        # 道悪実績があれば加点
                        if win_rate > 0.15:  # 勝率15%以上
                            adjustment += 0.03
                        elif win_rate > 0.05:
                            adjustment += 0.01

                        if top3_rate > 0.4:  # 複勝率40%以上
                            adjustment += 0.02
                        elif top3_rate > 0.2:
                            adjustment += 0.01

                        # 経験豊富ならさらに加点
                        if runs >= 5:
                            adjustment += 0.01

                    # 良馬場のみの馬は道悪で減点
                    if condition >= 2 and runs == 0:
                        # この馬場状態での出走がない
                        adjustment -= 0.02

        # スコア調整
        new_rank_score = score_data.get('rank_score', 999) - adjustment
        old_prob = score_data.get('win_probability', 0)
        new_prob = old_prob * (1 + adjustment * 3)
        new_prob = max(0.001, min(0.99, new_prob))

        adjusted_scores[umaban_str] = {
            'rank_score': new_rank_score,
            'win_probability': new_prob,
            'track_adjustment': adjustment,
        }

        # quinella_probabilityも調整
        if 'quinella_probability' in score_data:
            old_quinella = score_data['quinella_probability']
            new_quinella = old_quinella * (1 + adjustment * 2.5)
            new_quinella = max(0.005, min(0.99, new_quinella))
            adjusted_scores[umaban_str]['quinella_probability'] = new_quinella

        # place_probabilityも調整
        if 'place_probability' in score_data:
            old_place = score_data['place_probability']
            new_place = old_place * (1 + adjustment * 2)
            new_place = max(0.01, min(0.99, new_place))
            adjusted_scores[umaban_str]['place_probability'] = new_place

    # 調整馬がいない場合は元のスコアをそのまま返す
    adjusted_count = len([a for a in adjusted_scores.values() if a.get('track_adjustment', 0) != 0])
    logger.info(f"馬場状態調整完了: {condition_name}, 調整馬数={adjusted_count}")

    if adjusted_count == 0:
        return ml_scores

    # 確率を再正規化
    n_horses = len(adjusted_scores)

    # 勝率: 合計1.0
    win_sum = sum(s.get('win_probability', 0) for s in adjusted_scores.values())
    if win_sum > 0:
        for umaban_str in adjusted_scores:
            adjusted_scores[umaban_str]['win_probability'] /= win_sum

    # 連対率: 合計2.0
    quinella_sum = sum(s.get('quinella_probability', 0) for s in adjusted_scores.values())
    if quinella_sum > 0:
        expected_quinella = min(2.0, n_horses)  # 2頭以上なら常に2.0
        for umaban_str in adjusted_scores:
            if 'quinella_probability' in adjusted_scores[umaban_str]:
                adjusted_scores[umaban_str]['quinella_probability'] *= expected_quinella / quinella_sum

    # 複勝率: 合計3.0
    place_sum = sum(s.get('place_probability', 0) for s in adjusted_scores.values())
    if place_sum > 0:
        expected_place = min(3.0, n_horses)  # 3頭以上なら常に3.0
        for umaban_str in adjusted_scores:
            if 'place_probability' in adjusted_scores[umaban_str]:
                adjusted_scores[umaban_str]['place_probability'] *= expected_place / place_sum

    return adjusted_scores


def _is_mock_mode() -> bool:
    """モックモードかどうかを判定"""
    return os.getenv("DB_MODE", "local") == "mock"


def _extract_future_race_features(conn, race_id: str, extractor, year: int):
    """
    未来レースの特徴量を抽出

    確定データがない未来のレースに対して、登録済みの出走馬情報から特徴量を抽出する

    Args:
        conn: DB接続
        race_id: レースID
        extractor: FastFeatureExtractor
        year: 対象年

    Returns:
        pd.DataFrame: 特徴量DataFrame
    """
    import pandas as pd

    cur = conn.cursor()

    # 1. レース情報を取得（登録済みデータ）
    cur.execute('''
        SELECT race_code, kaisai_nen, kaisai_gappi, keibajo_code,
               kyori, track_code, grade_code,
               shiba_babajotai_code, dirt_babajotai_code
        FROM race_shosai
        WHERE race_code = %s
          AND data_kubun IN ('1', '2', '3', '4', '5', '6')
        LIMIT 1
    ''', (race_id,))

    race_row = cur.fetchone()
    if not race_row:
        cur.close()
        return pd.DataFrame()

    race_cols = [d[0] for d in cur.description]
    races = [dict(zip(race_cols, race_row))]

    # 2. 出走馬データを取得
    cur.execute('''
        SELECT
            race_code, umaban, wakuban, ketto_toroku_bango,
            seibetsu_code, barei, futan_juryo,
            blinker_shiyo_kubun, kishu_code, chokyoshi_code,
            bataiju, zogen_sa, bamei
        FROM umagoto_race_joho
        WHERE race_code = %s
          AND data_kubun IN ('1', '2', '3', '4', '5', '6')
        ORDER BY umaban::int
    ''', (race_id,))

    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    entries = [dict(zip(cols, row)) for row in rows]

    if not entries:
        cur.close()
        return pd.DataFrame()

    # 馬番0（取消馬・登録のみ）を除外
    valid_entries = []
    for e in entries:
        umaban = e.get('umaban', '00')
        try:
            if int(umaban) >= 1:
                valid_entries.append(e)
        except (ValueError, TypeError):
            pass
    entries = valid_entries

    logger.info(f"Future race entries: {len(entries)} horses")

    # 3. 過去成績を取得
    kettonums = [e['ketto_toroku_bango'] for e in entries if e.get('ketto_toroku_bango')]
    past_stats = extractor._get_past_stats_batch(kettonums)

    # 4. 騎手・調教師キャッシュ
    extractor._cache_jockey_trainer_stats(year)

    # 5. 追加データ
    jh_pairs = [(e.get('kishu_code', ''), e.get('ketto_toroku_bango', ''))
                for e in entries if e.get('kishu_code') and e.get('ketto_toroku_bango')]
    jockey_horse_stats = extractor._get_jockey_horse_combo_batch(jh_pairs)
    surface_stats = extractor._get_surface_stats_batch(kettonums)
    turn_stats = extractor._get_turn_rates_batch(kettonums)
    for kettonum, stats in turn_stats.items():
        if kettonum in past_stats:
            past_stats[kettonum]['right_turn_rate'] = stats['right_turn_rate']
            past_stats[kettonum]['left_turn_rate'] = stats['left_turn_rate']
            past_stats[kettonum]['right_turn_runs'] = stats.get('right_turn_runs', 0)
            past_stats[kettonum]['left_turn_runs'] = stats.get('left_turn_runs', 0)
    training_stats = extractor._get_training_stats_batch(kettonums)
    # 競馬場別成績（予測時は全データ使用 - entriesを渡さない）
    venue_stats = extractor._get_venue_stats_batch(kettonums)

    # 5.5 血統・種牡馬・騎手の新馬戦成績データ取得
    pedigree_info = extractor._get_pedigree_batch(kettonums)
    race_codes = [e['race_code'] for e in entries]
    zenso_info = extractor._get_zenso_batch(kettonums, race_codes, entries)
    jockey_codes = list(set(e.get('kishu_code', '') for e in entries if e.get('kishu_code')))
    jockey_recent = extractor._get_jockey_recent_batch(jockey_codes, year)

    # 種牡馬成績
    sire_ids = [p.get('sire_id', '') for p in pedigree_info.values() if p.get('sire_id')]
    sire_stats_turf = extractor._get_sire_stats_batch(sire_ids, year, is_turf=True)
    sire_stats_dirt = extractor._get_sire_stats_batch(sire_ids, year, is_turf=False)

    # 新馬・未勝利戦専用成績
    sire_maiden_stats = extractor._get_sire_maiden_stats_batch(sire_ids, year)
    jockey_maiden_stats = extractor._get_jockey_maiden_stats_batch(jockey_codes, year)
    logger.info(f"Maiden stats: sire={len(sire_maiden_stats)}, jockey={len(jockey_maiden_stats)}")

    # 6. 特徴量生成（ダミーの着順を設定）
    features_list = []
    for entry in entries:
        entry['kakutei_chakujun'] = '01'  # 予測用ダミー

        features = extractor._build_features(
            entry, races, past_stats,
            jockey_horse_stats=jockey_horse_stats,
            distance_stats=surface_stats,
            training_stats=training_stats,
            venue_stats=venue_stats,
            pedigree_info=pedigree_info,
            zenso_info=zenso_info,
            jockey_recent=jockey_recent,
            sire_stats_turf=sire_stats_turf,
            sire_stats_dirt=sire_stats_dirt,
            sire_maiden_stats=sire_maiden_stats,
            jockey_maiden_stats=jockey_maiden_stats,
            year=year
        )
        if features:
            features['bamei'] = entry.get('bamei', '')
            features_list.append(features)

    cur.close()

    if not features_list:
        return pd.DataFrame()

    return pd.DataFrame(features_list)


def _compute_ml_predictions(
    race_id: str,
    horses: List[Dict],
    bias_date: Optional[str] = None,
    is_final: bool = False
) -> Dict[str, Any]:
    """
    機械学習による予測を計算

    Args:
        race_id: レースID（16桁）
        horses: 出走馬リスト
        bias_date: バイアス適用日（YYYY-MM-DD形式、省略時は自動検出）
        is_final: 最終予想かどうか（Trueなら馬場状態を反映）

    Returns:
        Dict[馬番, {"rank_score": float, "win_probability": float}]
    """
    logger.info(f"Computing ML predictions: race_id={race_id}, horses={len(horses)}")

    try:
        from src.models.feature_extractor import FastFeatureExtractor
        from src.db.connection import get_db
        import pandas as pd
        import numpy as np
        import joblib

        # モデル読み込み
        if not ML_MODEL_PATH.exists():
            logger.warning(f"ML model not found: {ML_MODEL_PATH}")
            return {}

        model_data = joblib.load(ML_MODEL_PATH)

        # ensemble_modelのキーを取得（複数形式に対応）
        # 形式1: v2_enhanced_ensemble（新形式: 分類モデル+キャリブレーション）
        # 形式2: xgb_model, lgb_model（週次再学習形式）
        # 形式3: models.xgboost, models.lightgbm（旧形式）
        models_dict = model_data.get('models', {})
        version = model_data.get('version', '')

        # 回帰モデル取得
        if 'xgb_regressor' in models_dict:
            xgb_model = models_dict['xgb_regressor']
            lgb_model = models_dict.get('lgb_regressor')
        elif 'xgb_model' in model_data:
            xgb_model = model_data['xgb_model']
            lgb_model = model_data.get('lgb_model')
        elif 'xgboost' in models_dict:
            xgb_model = models_dict.get('xgboost')
            lgb_model = models_dict.get('lightgbm')
        else:
            logger.error(f"Invalid model format: ensemble_model required")
            return {}

        # 分類モデル・キャリブレーター取得（新形式のみ）
        xgb_win = models_dict.get('xgb_win')
        lgb_win = models_dict.get('lgb_win')
        xgb_quinella = models_dict.get('xgb_quinella')
        lgb_quinella = models_dict.get('lgb_quinella')
        xgb_place = models_dict.get('xgb_place')
        lgb_place = models_dict.get('lgb_place')
        win_calibrator = models_dict.get('win_calibrator')
        quinella_calibrator = models_dict.get('quinella_calibrator')
        place_calibrator = models_dict.get('place_calibrator')

        # CatBoostモデル取得（v5以降）
        cb_model = models_dict.get('cb_regressor')
        cb_win = models_dict.get('cb_win')
        cb_quinella = models_dict.get('cb_quinella')
        cb_place = models_dict.get('cb_place')
        has_catboost = cb_model is not None

        # アンサンブル重み（デフォルト: XGB+LGB均等）
        ensemble_weights = model_data.get('ensemble_weights', {
            'xgb': 0.5, 'lgb': 0.5, 'cb': 0.0
        })

        has_classifiers = xgb_win is not None and lgb_win is not None
        has_quinella = xgb_quinella is not None and lgb_quinella is not None

        feature_names = model_data.get('feature_names', [])
        logger.info(f"Ensemble model loaded: {ML_MODEL_PATH}, features={len(feature_names)}, "
                   f"CatBoost={'あり' if has_catboost else 'なし'}")

        # DB接続を取得
        db = get_db()
        conn = db.get_connection()

        if not conn:
            logger.warning("DB connection failed for ML prediction")
            return {}

        try:
            # 特徴量抽出（ML学習時と同じFastFeatureExtractorを使用）
            extractor = FastFeatureExtractor(conn)
            year = int(race_id[:4])
            logger.info(f"Extracting features for race {race_id}...")

            # まず確定済みデータから試行（過去レース）
            df = extractor.extract_year_data(year, max_races=10000)
            race_df = df[df['race_code'] == race_id].copy() if len(df) > 0 else pd.DataFrame()

            # 確定データがない場合、未来レースとして直接特徴量抽出
            if len(race_df) == 0:
                logger.info(f"No confirmed data, extracting features for future race: {race_id}")
                race_df = _extract_future_race_features(conn, race_id, extractor, year)

            if len(race_df) == 0:
                logger.warning(f"No data for race: {race_id}")
                return {}

            logger.info(f"Found {len(race_df)} horses for race {race_id}")

            # モデルが期待する特徴量のみを抽出
            available_features = [f for f in feature_names if f in race_df.columns]
            missing_features = [f for f in feature_names if f not in race_df.columns]
            if missing_features:
                logger.warning(f"Missing features: {missing_features[:5]}...")
                for f in missing_features:
                    race_df[f] = 0

            X = race_df[feature_names].fillna(0)
            features_list = race_df.to_dict('records')

            # ML予測（ensemble_model: XGBoost + LightGBM + CatBoost）
            if not xgb_model or not lgb_model:
                logger.error("Ensemble model requires both XGBoost and LightGBM")
                return {}

            # 回帰予測（着順スコア）
            xgb_pred = xgb_model.predict(X)
            lgb_pred = lgb_model.predict(X)

            # CatBoostがある場合は3モデルアンサンブル
            if has_catboost:
                cb_pred = cb_model.predict(X)
                w = ensemble_weights
                rank_scores = (xgb_pred * w['xgb'] + lgb_pred * w['lgb'] + cb_pred * w['cb'])
            else:
                # 後方互換: XGB+LGBのみ
                w = ensemble_weights
                xgb_w = w.get('xgb', 0.5)
                lgb_w = w.get('lgb', 0.5)
                total = xgb_w + lgb_w
                rank_scores = (xgb_pred * xgb_w + lgb_pred * lgb_w) / total

            # 分類モデルがある場合は確率を直接予測
            if has_classifiers:
                logger.info("Using classification models for probability prediction")
                n_horses = len(X)

                # 勝利確率
                xgb_win_prob = xgb_win.predict_proba(X)[:, 1]
                lgb_win_prob = lgb_win.predict_proba(X)[:, 1]

                if has_catboost and cb_win is not None:
                    cb_win_prob = cb_win.predict_proba(X)[:, 1]
                    w = ensemble_weights
                    win_probs = (xgb_win_prob * w['xgb'] + lgb_win_prob * w['lgb'] + cb_win_prob * w['cb'])
                else:
                    w = ensemble_weights
                    xgb_w = w.get('xgb', 0.5)
                    lgb_w = w.get('lgb', 0.5)
                    total = xgb_w + lgb_w
                    win_probs = (xgb_win_prob * xgb_w + lgb_win_prob * lgb_w) / total

                # 連対確率（モデルがあれば使用、なければ推定）
                if has_quinella:
                    xgb_quinella_prob = xgb_quinella.predict_proba(X)[:, 1]
                    lgb_quinella_prob = lgb_quinella.predict_proba(X)[:, 1]

                    if has_catboost and cb_quinella is not None:
                        cb_quinella_prob = cb_quinella.predict_proba(X)[:, 1]
                        w = ensemble_weights
                        quinella_probs = (xgb_quinella_prob * w['xgb'] + lgb_quinella_prob * w['lgb'] + cb_quinella_prob * w['cb'])
                    else:
                        w = ensemble_weights
                        xgb_w = w.get('xgb', 0.5)
                        lgb_w = w.get('lgb', 0.5)
                        total = xgb_w + lgb_w
                        quinella_probs = (xgb_quinella_prob * xgb_w + lgb_quinella_prob * lgb_w) / total
                else:
                    # 旧モデル互換: 勝率と複勝率から推定
                    quinella_probs = None

                # 複勝確率
                xgb_place_prob = xgb_place.predict_proba(X)[:, 1]
                lgb_place_prob = lgb_place.predict_proba(X)[:, 1]

                if has_catboost and cb_place is not None:
                    cb_place_prob = cb_place.predict_proba(X)[:, 1]
                    w = ensemble_weights
                    place_probs = (xgb_place_prob * w['xgb'] + lgb_place_prob * w['lgb'] + cb_place_prob * w['cb'])
                else:
                    w = ensemble_weights
                    xgb_w = w.get('xgb', 0.5)
                    lgb_w = w.get('lgb', 0.5)
                    total = xgb_w + lgb_w
                    place_probs = (xgb_place_prob * xgb_w + lgb_place_prob * lgb_w) / total

                # キャリブレーション適用（モデル内蔵キャリブレーター）
                if win_calibrator is not None:
                    win_probs = win_calibrator.predict(win_probs)
                    logger.info("Applied win_calibrator")
                if quinella_calibrator is not None and quinella_probs is not None:
                    quinella_probs = quinella_calibrator.predict(quinella_probs)
                    logger.info("Applied quinella_calibrator")
                if place_calibrator is not None:
                    place_probs = place_calibrator.predict(place_probs)
                    logger.info("Applied place_calibrator")

                # 確率の正規化（各確率を独立して正規化）
                # 勝率: 合計を1.0に（1頭だけが勝つ）
                win_sum = win_probs.sum()
                if win_sum > 0:
                    win_probs = win_probs / win_sum

                # 連対率: 合計を2.0に（2頭が2着以内）
                if quinella_probs is not None:
                    expected_quinella_sum = min(2.0, n_horses)
                    quinella_sum = quinella_probs.sum()
                    if quinella_sum > 0:
                        quinella_probs = quinella_probs * expected_quinella_sum / quinella_sum

                # 複勝率: 合計を3.0に（3頭が3着以内）
                expected_place_sum = min(3.0, n_horses)
                place_sum = place_probs.sum()
                if place_sum > 0:
                    place_probs = place_probs * expected_place_sum / place_sum
            else:
                # 旧形式: スコアを確率に変換（softmax風）
                logger.info("Using regression scores for probability (legacy mode)")
                scores_exp = np.exp(-rank_scores)
                win_probs = scores_exp / scores_exp.sum()
                quinella_probs = None
                place_probs = None

            # 結果を辞書形式に変換
            ml_scores = {}
            for i, features in enumerate(features_list):
                horse_num = features.get('umaban', i + 1)
                score_data = {
                    "rank_score": float(rank_scores[i]),
                    "win_probability": float(min(1.0, win_probs[i]))  # クリップ
                }
                if quinella_probs is not None:
                    # 個別確率は1.0を超えないようクリップ
                    score_data["quinella_probability"] = float(min(1.0, quinella_probs[i]))
                if place_probs is not None:
                    # 個別確率は1.0を超えないようクリップ
                    score_data["place_probability"] = float(min(1.0, place_probs[i]))
                ml_scores[str(horse_num)] = score_data

            logger.info(f"ML predictions computed: {len(ml_scores)} horses")

            # デバッグ: ML scores の確認
            sample_scores = list(ml_scores.items())[:3]
            for umaban, data in sample_scores:
                logger.info(f"DEBUG ml_score[{umaban}]: win={data.get('win_probability', 0)*100:.4f}%")

            # バイアス適用
            # 優先順位:
            # 1. パラメータ bias_date が渡されていればそれを使用
            # 2. 環境変数 KEIBA_BIAS_DATE が設定されていればそれを使用
            # 3. なければ日曜レースの場合に前日土曜のバイアスを自動検索
            import os
            from datetime import date, timedelta

            # パラメータ or 環境変数からバイアス日を決定
            bias_date_str = bias_date or os.environ.get('KEIBA_BIAS_DATE')

            if bias_date_str:
                # 指定されたバイアスを使用
                bias_data = _load_bias_for_date(bias_date_str)
                if bias_data:
                    logger.info(f"バイアス適用: {bias_date_str}")
                    ml_scores = _apply_bias_to_scores(
                        ml_scores, race_id, horses, bias_data
                    )
                else:
                    logger.warning(f"バイアスファイル未発見: {bias_date_str}")
            else:
                # 自動検出モード（日曜レースなら前日土曜）
                race_year = int(race_id[:4])
                race_month = int(race_id[6:8])
                race_day = int(race_id[8:10])
                try:
                    race_date = date(race_year, race_month, race_day)
                    if race_date.weekday() == 6:  # Sunday
                        saturday_date = race_date - timedelta(days=1)
                        bias_data = _load_bias_for_date(saturday_date.isoformat())
                        if bias_data:
                            logger.info(f"自動検出バイアス適用: {saturday_date}")
                            ml_scores = _apply_bias_to_scores(
                                ml_scores, race_id, horses, bias_data
                            )
                except (ValueError, IndexError) as e:
                    logger.warning(f"バイアス適用スキップ: {e}")

            # 最終予想時は馬場状態調整を適用
            if is_final:
                logger.info("最終予想: 馬場状態調整を適用")
                track_condition = _get_current_track_condition(conn, race_id)
                if track_condition and track_condition.get('condition', 0) > 0:
                    # 出走馬の血統登録番号を取得
                    kettonums = [h.get('ketto_toroku_bango', '') for h in horses if h.get('ketto_toroku_bango')]
                    if kettonums:
                        baba_performance = _get_horse_baba_performance(
                            conn,
                            kettonums,
                            track_condition['track_type'],
                            track_condition['condition']
                        )
                        if baba_performance:
                            ml_scores = _apply_track_condition_adjustment(
                                ml_scores, horses, track_condition, baba_performance
                            )
                else:
                    logger.info("馬場状態データなし、調整スキップ")

            return ml_scores

        finally:
            conn.close()

    except Exception as e:
        logger.error(f"ML prediction failed: {e}")
        return {}


def _generate_mock_prediction(race_id: str, is_final: bool) -> PredictionResponse:
    """モック予想を生成（確率ベース・ランキング形式）"""
    logger.info(f"[MOCK] Generating mock prediction for race_id={race_id}")

    # モックのランキングデータ
    mock_horses = [
        {"rank": 1, "horse_number": 1, "horse_name": "モックホース1", "win_prob": 0.25},
        {"rank": 2, "horse_number": 5, "horse_name": "モックホース5", "win_prob": 0.18},
        {"rank": 3, "horse_number": 3, "horse_name": "モックホース3", "win_prob": 0.12},
        {"rank": 4, "horse_number": 7, "horse_name": "モックホース7", "win_prob": 0.10},
        {"rank": 5, "horse_number": 2, "horse_name": "モックホース2", "win_prob": 0.08},
    ]

    ranked_horses = [
        HorseRankingEntry(
            rank=h["rank"],
            horse_number=h["horse_number"],
            horse_name=h["horse_name"],
            win_probability=h["win_prob"],
            quinella_probability=min(h["win_prob"] * 1.8, 0.5),
            place_probability=min(h["win_prob"] * 2.5, 0.6),
            position_distribution=PositionDistribution(
                first=h["win_prob"],
                second=h["win_prob"] * 0.8,
                third=h["win_prob"] * 0.6,
                out_of_place=max(0, 1.0 - h["win_prob"] * 2.4),
            ),
            rank_score=float(h["rank"]),
            confidence=0.7 - h["rank"] * 0.05,
        )
        for h in mock_horses
    ]

    prediction_result = PredictionResult(
        ranked_horses=ranked_horses,
        prediction_confidence=0.72,
        model_info="mock_model",
    )

    return PredictionResponse(
        prediction_id=str(uuid.uuid4()),
        race_id=race_id,
        race_name="モックレース",
        race_date=datetime.now().strftime("%Y-%m-%d"),
        venue="東京",
        race_number="11",
        race_time="15:40",
        prediction_result=prediction_result,
        predicted_at=datetime.now(),
        is_final=is_final,
    )


def _generate_ml_only_prediction(
    race_data: Dict[str, Any],
    ml_scores: Dict[str, Any]
) -> Dict[str, Any]:
    """
    MLスコアから確率ベース・ランキング形式の予想結果を生成

    Args:
        race_data: レースデータ
        ml_scores: ML予測スコア

    Returns:
        Dict: 確率ベース・ランキング形式の予想データ
    """
    horses = race_data.get("horses", [])
    n_horses = len(horses)

    # MLスコアでソート（スコアが低いほど上位）
    scored_horses = []
    for horse in horses:
        umaban_raw = horse.get("umaban", "")
        # 馬番を正規化（'01' -> '1'、1 -> '1' 等）
        try:
            umaban = str(int(umaban_raw))
        except (ValueError, TypeError):
            umaban = str(umaban_raw)
        score_data = ml_scores.get(umaban, {})
        # 性別コード変換
        sex_code = horse.get("seibetsu_code", "")
        sex_map = {"1": "牡", "2": "牝", "3": "セ"}
        horse_sex = sex_map.get(str(sex_code), "")

        # 馬齢
        barei = horse.get("barei", "")
        try:
            horse_age = int(barei) if barei else None
        except (ValueError, TypeError):
            horse_age = None

        # 馬番0は取消馬または登録のみなのでスキップ
        horse_num = int(umaban) if umaban.isdigit() else 0
        if horse_num < 1:
            continue

        scored_horses.append({
            "horse_number": horse_num,
            "horse_name": horse.get("bamei", "不明"),
            "horse_sex": horse_sex,
            "horse_age": horse_age,
            "jockey_name": horse.get("kishumei", ""),
            "rank_score": score_data.get("rank_score", 999),
            "win_probability": score_data.get("win_probability", 0.0),
            "quinella_probability": score_data.get("quinella_probability"),  # モデルからの連対確率（あれば）
            "place_probability": score_data.get("place_probability"),  # モデルからの複勝確率（あれば）
        })

    # 勝率順にソート（勝率が高い馬が上位）
    # 注意: rank_scoreではなくwin_probabilityを使用することで、
    # ユーザーに表示される勝率と順位が一致する
    scored_horses.sort(key=lambda x: x["win_probability"], reverse=True)

    # 順位分布を計算
    def calc_position_distribution(
        win_prob: float,
        quinella_prob: Optional[float],
        place_prob: Optional[float],
        rank: int,
        n: int
    ) -> Dict[str, float]:
        """順位分布を推定（勝率・連対率・複勝率から算出）

        連対率モデルがある場合:
          2着確率 = 連対率 - 勝率
          3着確率 = 複勝率 - 連対率
        """
        # 1着確率 = 勝率
        first = win_prob

        if quinella_prob is not None and place_prob is not None:
            # 連対率・複勝率モデルがある場合、直接計算
            second = max(0, quinella_prob - first)
            third = max(0, place_prob - quinella_prob)
        elif place_prob is not None:
            # 連対率がない場合（旧形式互換）
            remaining_place = max(0, place_prob - first)
            if rank <= 3:
                second = remaining_place * 0.55
                third = remaining_place * 0.45
            elif rank <= 6:
                second = remaining_place * 0.5
                third = remaining_place * 0.5
            else:
                second = remaining_place * 0.45
                third = remaining_place * 0.55
        else:
            # 旧形式: 勝率ベースで推定
            second = min(win_prob * 1.5, 0.3) if rank <= 5 else win_prob * 0.5
            third = min(win_prob * 1.8, 0.35) if rank <= 7 else win_prob * 0.3

        # 4着以下
        out = max(0.0, 1.0 - first - second - third)
        return {
            "first": round(first, 4),
            "second": round(second, 4),
            "third": round(third, 4),
            "out_of_place": round(out, 4),
        }

    # ランキングエントリを生成
    # 注意: 確率はすでにモデルで予測・正規化済み
    # - 勝率: 合計1.0
    # - 連対率: 合計2.0
    # - 複勝率: 合計3.0
    ranked_horses = []
    for i, h in enumerate(scored_horses):
        rank = i + 1
        win_prob = h["win_probability"]
        model_quinella_prob = h.get("quinella_probability")  # モデルからの連対確率
        model_place_prob = h.get("place_probability")  # モデルからの複勝確率

        # 順位分布を計算（表示用）- 連対率モデルを使用
        pos_dist = calc_position_distribution(win_prob, model_quinella_prob, model_place_prob, rank, n_horses)

        # 連対率: モデルからの値を優先、なければ分布から計算
        if model_quinella_prob is not None:
            quinella_prob = model_quinella_prob
        else:
            quinella_prob = min(1.0, pos_dist["first"] + pos_dist["second"])

        # 複勝率: モデルからの値を優先、なければ分布から計算
        if model_place_prob is not None:
            place_prob = model_place_prob
        else:
            place_prob = min(1.0, pos_dist["first"] + pos_dist["second"] + pos_dist["third"])

        # 個別の信頼度（データの完全性と確率の分離度から算出）
        # 勝率が次の馬と十分に離れているかで信頼度を評価
        if i < len(scored_horses) - 1:
            prob_gap = h["win_probability"] - scored_horses[i + 1]["win_probability"]
            # 確率の差に基づいて信頼度を計算（0.0〜0.95）
            confidence = min(0.95, max(0.1, 0.5 + prob_gap * 5))
        else:
            confidence = 0.5

        ranked_horses.append({
            "rank": rank,
            "horse_number": h["horse_number"],
            "horse_name": h["horse_name"],
            "horse_sex": h.get("horse_sex", ""),
            "horse_age": h.get("horse_age"),
            "jockey_name": h.get("jockey_name", ""),
            "win_probability": round(win_prob, 4),
            "quinella_probability": round(quinella_prob, 4),
            "place_probability": round(place_prob, 4),
            "position_distribution": pos_dist,
            "rank_score": round(h["rank_score"], 4),
            "confidence": round(confidence, 4),
        })

    # 予測全体の信頼度（トップ馬の勝率と2位との差から算出）
    if len(scored_horses) >= 2:
        top_prob = scored_horses[0]["win_probability"]
        second_prob = scored_horses[1]["win_probability"]
        gap_ratio = (top_prob - second_prob) / max(top_prob, 0.01)
        prediction_confidence = min(0.95, 0.4 + gap_ratio * 0.5 + top_prob)
    else:
        prediction_confidence = 0.5

    # 複数ランキングを生成（目的別）
    # 連対率順（馬連・ワイド向け）
    quinella_ranking = sorted(
        [(h["horse_number"], h["quinella_probability"]) for h in ranked_horses],
        key=lambda x: x[1], reverse=True
    )[:5]  # Top5

    # 複勝率順（複勝向け）
    place_ranking = sorted(
        [(h["horse_number"], h["place_probability"]) for h in ranked_horses],
        key=lambda x: x[1], reverse=True
    )[:5]  # Top5

    # 穴馬候補（複勝率高いが勝率低い = 勝ち切れないが3着には来る）
    # 複勝率 >= 20% かつ 勝率 < 10%
    dark_horses = [
        {"horse_number": h["horse_number"], "win_prob": h["win_probability"],
         "place_prob": h["place_probability"]}
        for h in ranked_horses
        if h["place_probability"] >= 0.20 and h["win_probability"] < 0.10
    ][:3]

    return {
        "ranked_horses": ranked_horses,  # 勝率順（単勝向け）
        "quinella_ranking": [{"rank": i+1, "horse_number": num, "quinella_prob": round(prob, 4)}
                            for i, (num, prob) in enumerate(quinella_ranking)],
        "place_ranking": [{"rank": i+1, "horse_number": num, "place_prob": round(prob, 4)}
                          for i, (num, prob) in enumerate(place_ranking)],
        "dark_horses": dark_horses,  # 穴馬候補
        "prediction_confidence": round(prediction_confidence, 4),
        "model_info": "ensemble_model",
    }


async def generate_prediction(
    race_id: str,
    is_final: bool = False,
    bias_date: Optional[str] = None
) -> PredictionResponse:
    """
    予想生成のメイン関数（MLモデルのみ使用、LLM不使用）
    確率ベース・ランキング形式・順位分布・信頼度スコアを出力

    Args:
        race_id: レースID（16桁）
        is_final: 最終予想フラグ（馬体重後）
        bias_date: バイアス適用日（YYYY-MM-DD形式、省略時は自動検出）

    Returns:
        PredictionResponse: 予想結果（確率ベース・ランキング形式）

    Raises:
        PredictionError: 予想生成に失敗した場合
    """
    logger.info(f"Starting ML prediction: race_id={race_id}, is_final={is_final}")

    # モックモードの場合
    if _is_mock_mode():
        return _generate_mock_prediction(race_id, is_final)

    try:
        # 遅延インポート（モック時は不要）
        from src.db.async_connection import get_connection
        from src.db.queries import (
            get_race_prediction_data,
            check_race_exists,
        )

        # 1. データ取得
        async with get_connection() as conn:
            # レースの存在チェック
            exists = await check_race_exists(conn, race_id)
            if not exists:
                raise MissingDataError(f"レースが見つかりません: race_id={race_id}")

            # 予想データを取得
            logger.debug(f"Fetching race prediction data: race_id={race_id}")
            race_data = await get_race_prediction_data(conn, race_id)

            if not race_data or not race_data.get("horses"):
                raise MissingDataError(
                    f"レースデータが不足しています: race_id={race_id}"
                )

        # 2. ML予測を計算
        ml_scores = {}
        try:
            ml_scores = _compute_ml_predictions(
                race_id, race_data.get("horses", []), bias_date, is_final=is_final
            )
            if ml_scores:
                logger.info(f"ML predictions computed: {len(ml_scores)} horses")
            else:
                raise PredictionError("ML予測が利用できません")
        except Exception as e:
            logger.error(f"ML prediction failed: {e}")
            raise PredictionError(f"ML予測に失敗しました: {e}") from e

        # 3. MLスコアから確率ベース・ランキング形式の予想結果を生成
        logger.debug("Generating probability-based ranking prediction")
        ml_result = _generate_ml_only_prediction(
            race_data=race_data,
            ml_scores=ml_scores
        )

        # 4. 予想結果をPydanticモデルに変換
        logger.debug("Converting ML result to PredictionResponse")
        prediction_response = _convert_to_prediction_response(
            race_data=race_data,
            ml_result=ml_result,
            is_final=is_final
        )

        # 5. DBに保存
        prediction_id = await save_prediction(prediction_response)
        prediction_response.prediction_id = prediction_id

        logger.info(f"ML prediction completed: prediction_id={prediction_id}")
        return prediction_response

    except MissingDataError:
        raise
    except PredictionError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during prediction generation: {e}")
        raise PredictionError(f"予想生成中にエラーが発生しました: {e}") from e


async def save_prediction(prediction_data: PredictionResponse) -> str:
    """
    予想結果をDBに保存

    Args:
        prediction_data: 予想結果

    Returns:
        str: 予想ID

    Raises:
        DatabaseQueryError: DB保存に失敗した場合
    """
    logger.debug(f"Saving prediction: race_id={prediction_data.race_id}")

    # モックモードの場合はUUIDを生成して返すだけ
    if _is_mock_mode():
        prediction_id = str(uuid.uuid4())
        logger.info(f"[MOCK] Prediction saved: prediction_id={prediction_id}")
        return prediction_id

    try:
        from src.db.async_connection import get_connection

        async with get_connection() as conn:
            # predictions テーブルに保存（UPSERT: race_id + is_final でユニーク）
            sql = """
                INSERT INTO predictions (
                    prediction_id,
                    race_id,
                    race_date,
                    is_final,
                    prediction_result,
                    predicted_at
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (race_id, is_final) DO UPDATE SET
                    prediction_result = EXCLUDED.prediction_result,
                    predicted_at = EXCLUDED.predicted_at
                RETURNING prediction_id;
            """

            # prediction_id を生成（UUIDベース）
            prediction_id = str(uuid.uuid4())

            # prediction_result をdict形式で取得（asyncpgがJSONBに自動変換）
            import json
            prediction_result_dict = prediction_data.prediction_result.model_dump()

            # race_date を date型に変換
            from datetime import date as date_type
            if isinstance(prediction_data.race_date, str):
                race_date = date_type.fromisoformat(prediction_data.race_date)
            else:
                race_date = prediction_data.race_date

            result = await conn.fetchrow(
                sql,
                prediction_id,
                prediction_data.race_id,
                race_date,
                prediction_data.is_final,
                json.dumps(prediction_result_dict),  # asyncpg JSONB用にJSON文字列
                prediction_data.predicted_at,
            )

            if not result:
                raise DatabaseQueryError("予想結果の保存に失敗しました")

            saved_id = result["prediction_id"]
            logger.info(f"Prediction saved/updated: prediction_id={saved_id}")
            return saved_id

    except asyncpg.PostgresError as e:
        logger.error(f"Database error while saving prediction: {e}")
        raise DatabaseQueryError(f"予想結果の保存に失敗しました: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error while saving prediction: {e}")
        raise DatabaseQueryError(f"予想結果の保存中にエラーが発生しました: {e}") from e


async def get_prediction_by_id(prediction_id: str) -> Optional[PredictionResponse]:
    """
    保存済み予想を取得

    Args:
        prediction_id: 予想ID

    Returns:
        PredictionResponse: 予想結果（見つからない場合はNone）

    Raises:
        DatabaseQueryError: DB取得に失敗した場合
    """
    logger.debug(f"Fetching prediction: prediction_id={prediction_id}")

    # モックモードの場合
    if _is_mock_mode():
        logger.info(f"[MOCK] Prediction not found (mock mode): prediction_id={prediction_id}")
        return None

    try:
        from src.db.async_connection import get_connection
        from src.db.queries import get_race_info

        async with get_connection() as conn:
            sql = """
                SELECT
                    prediction_id,
                    race_id,
                    race_date,
                    is_final,
                    prediction_result,
                    predicted_at
                FROM predictions
                WHERE prediction_id = $1;
            """

            row = await conn.fetchrow(sql, prediction_id)

            if not row:
                logger.debug(f"Prediction not found: prediction_id={prediction_id}")
                return None

            # レース情報を取得（race_name等）
            race_info = await get_race_info(conn, row["race_id"])

            if not race_info:
                logger.warning(
                    f"Race info not found for prediction: race_id={row['race_id']}"
                )
                # デフォルト値を使用
                race_name = "不明"
                venue = "不明"
                race_number = "?"
                race_time = "00:00"
            else:
                race_name_raw = race_info.get(COL_RACE_NAME)
                # レース名が空の場合は条件コードからフォールバック生成
                if race_name_raw and race_name_raw.strip():
                    race_name = race_name_raw.strip()
                else:
                    # 競走条件からレース名を推測
                    kyoso_joken = race_info.get("kyoso_joken_code", "")
                    kyoso_shubetsu = race_info.get("kyoso_shubetsu_code", "")
                    # JRA-VANマスターに基づくマッピング
                    joken_map = {
                        "005": "1勝クラス", "010": "2勝クラス", "016": "3勝クラス",
                        "701": "新馬", "702": "未出走", "703": "未勝利", "999": "OP"
                    }
                    # 新馬・未勝利は「以上」なし、クラス戦は「以上」あり
                    if kyoso_joken in ("701", "702", "703"):
                        shubetsu_map = {"11": "2歳", "12": "3歳", "13": "3歳", "14": "4歳"}
                    else:
                        shubetsu_map = {"11": "2歳", "12": "3歳", "13": "3歳以上", "14": "4歳以上"}
                    shubetsu_name = shubetsu_map.get(kyoso_shubetsu, "")
                    joken_name = joken_map.get(kyoso_joken, "条件戦")
                    race_name = f"{shubetsu_name}{joken_name}".strip() or "条件戦"

                venue_code = race_info.get(COL_JYOCD, "00")
                venue = VENUE_CODE_MAP.get(venue_code, f"競馬場{venue_code}")
                race_number = str(race_info.get("race_bango", "?"))
                race_time = race_info.get("hasso_jikoku", "00:00")

            # PredictionResponse に変換
            prediction_result_data = row["prediction_result"]
            # 文字列として保存されている場合はパース
            if isinstance(prediction_result_data, str):
                import json
                try:
                    prediction_result_data = json.loads(prediction_result_data)
                except json.JSONDecodeError:
                    prediction_result_data = {"ranked_horses": [], "prediction_confidence": 0.5, "model_info": "unknown"}
            # ランキングエントリを構築
            ranked_horses = [
                HorseRankingEntry(
                    rank=h["rank"],
                    horse_number=h["horse_number"],
                    horse_name=h["horse_name"],
                    horse_sex=h.get("horse_sex"),
                    horse_age=h.get("horse_age"),
                    jockey_name=h.get("jockey_name"),
                    win_probability=h["win_probability"],
                    quinella_probability=h.get("quinella_probability", h["win_probability"] + h.get("position_distribution", {}).get("second", 0)),
                    place_probability=h["place_probability"],
                    position_distribution=PositionDistribution(**h["position_distribution"]),
                    rank_score=h["rank_score"],
                    confidence=h["confidence"],
                )
                for h in prediction_result_data.get("ranked_horses", [])
            ]
            prediction_result = PredictionResult(
                ranked_horses=ranked_horses,
                quinella_ranking=prediction_result_data.get("quinella_ranking"),
                place_ranking=prediction_result_data.get("place_ranking"),
                dark_horses=prediction_result_data.get("dark_horses"),
                prediction_confidence=prediction_result_data.get("prediction_confidence", 0.5),
                model_info=prediction_result_data.get("model_info", "unknown"),
            )

            # race_dateを文字列に変換
            race_date_raw = row["race_date"]
            if hasattr(race_date_raw, 'isoformat'):
                race_date_str = race_date_raw.isoformat()
            else:
                race_date_str = str(race_date_raw)

            prediction_response = PredictionResponse(
                prediction_id=row["prediction_id"],
                race_id=row["race_id"],
                race_name=race_name,
                race_date=race_date_str,
                venue=venue,
                race_number=race_number,
                race_time=race_time,
                prediction_result=prediction_result,
                predicted_at=row["predicted_at"],
                is_final=row["is_final"],
            )

            logger.info(f"Prediction fetched: prediction_id={prediction_id}")
            return prediction_response

    except asyncpg.PostgresError as e:
        logger.error(f"Database error while fetching prediction: {e}")
        raise DatabaseQueryError(f"予想結果の取得に失敗しました: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error while fetching prediction: {e}")
        raise DatabaseQueryError(f"予想結果の取得中にエラーが発生しました: {e}") from e


async def get_predictions_by_race(
    race_id: str,
    is_final: Optional[bool] = None
) -> List[PredictionHistoryItem]:
    """
    レースの予想履歴を取得

    Args:
        race_id: レースID
        is_final: 最終予想フラグでフィルタ（None の場合は全件）

    Returns:
        List[PredictionHistoryItem]: 予想履歴リスト

    Raises:
        DatabaseQueryError: DB取得に失敗した場合
    """
    logger.debug(f"Fetching predictions by race: race_id={race_id}, is_final={is_final}")

    # モックモードの場合
    if _is_mock_mode():
        logger.info(f"[MOCK] No predictions (mock mode): race_id={race_id}")
        return []

    try:
        from src.db.async_connection import get_connection

        async with get_connection() as conn:
            if is_final is None:
                sql = """
                    SELECT
                        prediction_id,
                        predicted_at,
                        is_final,
                        prediction_result
                    FROM predictions
                    WHERE race_id = $1
                    ORDER BY predicted_at DESC;
                """
                rows = await conn.fetch(sql, race_id)
            else:
                sql = """
                    SELECT
                        prediction_id,
                        predicted_at,
                        is_final,
                        prediction_result
                    FROM predictions
                    WHERE race_id = $1 AND is_final = $2
                    ORDER BY predicted_at DESC;
                """
                rows = await conn.fetch(sql, race_id, is_final)

            predictions = []
            for row in rows:
                pred_result = row["prediction_result"]
                # 文字列として保存されている場合はパース
                if isinstance(pred_result, str):
                    import json
                    try:
                        pred_result = json.loads(pred_result)
                    except json.JSONDecodeError:
                        pred_result = {}
                confidence = pred_result.get("prediction_confidence", 0.5) if pred_result else 0.5
                predictions.append(
                    PredictionHistoryItem(
                        prediction_id=row["prediction_id"],
                        predicted_at=row["predicted_at"],
                        is_final=row["is_final"],
                        prediction_confidence=confidence,
                    )
                )

            logger.info(
                f"Predictions fetched: race_id={race_id}, count={len(predictions)}"
            )
            return predictions

    except asyncpg.PostgresError as e:
        logger.error(f"Database error while fetching predictions: {e}")
        raise DatabaseQueryError(f"予想履歴の取得に失敗しました: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error while fetching predictions: {e}")
        raise DatabaseQueryError(f"予想履歴の取得中にエラーが発生しました: {e}") from e


def _convert_to_prediction_response(
    race_data: Dict[str, Any],
    ml_result: Dict[str, Any],
    is_final: bool
) -> PredictionResponse:
    """
    ML結果を確率ベース・ランキング形式のPredictionResponseに変換

    Args:
        race_data: レースデータ
        ml_result: ML予想結果（確率ベース・ランキング形式）
        is_final: 最終予想フラグ

    Returns:
        PredictionResponse: 変換後の予想結果
    """
    race_info = race_data.get("race", {})

    # レース情報を抽出
    race_id = race_info.get(COL_RACE_ID, "")
    race_name_raw = race_info.get(COL_RACE_NAME)
    # レース名が空の場合は条件コードからフォールバック生成
    if race_name_raw and race_name_raw.strip():
        race_name = race_name_raw.strip()
    else:
        # 競走条件からレース名を推測
        kyoso_joken = race_info.get("kyoso_joken_code", "")
        kyoso_shubetsu = race_info.get("kyoso_shubetsu_code", "")
        # JRA-VANマスターに基づくマッピング
        joken_map = {
            "005": "1勝クラス", "010": "2勝クラス", "016": "3勝クラス",
            "701": "新馬", "702": "未出走", "703": "未勝利", "999": "OP"
        }
        # 新馬・未勝利は「以上」なし、クラス戦は「以上」あり
        if kyoso_joken in ("701", "702", "703"):
            shubetsu_map = {"11": "2歳", "12": "3歳", "13": "3歳", "14": "4歳"}
        else:
            shubetsu_map = {"11": "2歳", "12": "3歳", "13": "3歳以上", "14": "4歳以上"}
        shubetsu_name = shubetsu_map.get(kyoso_shubetsu, "")
        joken_name = joken_map.get(kyoso_joken, "条件戦")
        race_name = f"{shubetsu_name}{joken_name}".strip() or "条件戦"

    venue_code = race_info.get(COL_JYOCD, "00")
    venue = VENUE_CODE_MAP.get(venue_code, f"競馬場{venue_code}")
    race_number = str(race_info.get("race_bango", "?"))
    race_time = race_info.get("hasso_jikoku", "00:00")

    # 開催日を計算
    kaisai_year = race_info.get(COL_KAISAI_YEAR, "")
    kaisai_monthday = race_info.get(COL_KAISAI_MONTHDAY, "")
    if kaisai_year and kaisai_monthday:
        race_date = f"{kaisai_year}-{kaisai_monthday[:2]}-{kaisai_monthday[2:]}"
    else:
        race_date = datetime.now().strftime("%Y-%m-%d")

    # ランキングエントリを構築
    ranked_horses_data = ml_result.get("ranked_horses", [])
    ranked_horses = [
        HorseRankingEntry(
            rank=h["rank"],
            horse_number=h["horse_number"],
            horse_name=h["horse_name"],
            horse_sex=h.get("horse_sex"),
            horse_age=h.get("horse_age"),
            jockey_name=h.get("jockey_name", ""),
            win_probability=h["win_probability"],
            quinella_probability=h["quinella_probability"],
            place_probability=h["place_probability"],
            position_distribution=PositionDistribution(**h["position_distribution"]),
            rank_score=h["rank_score"],
            confidence=h["confidence"],
        )
        for h in ranked_horses_data
    ]

    # PredictionResult を構築（確率ベース・ランキング形式）
    prediction_result = PredictionResult(
        ranked_horses=ranked_horses,
        quinella_ranking=ml_result.get("quinella_ranking"),
        place_ranking=ml_result.get("place_ranking"),
        dark_horses=ml_result.get("dark_horses"),
        prediction_confidence=ml_result.get("prediction_confidence", 0.5),
        model_info=ml_result.get("model_info", "ensemble_model"),
    )

    # PredictionResponse を構築
    prediction_response = PredictionResponse(
        prediction_id="",  # save_prediction で設定される
        race_id=race_id,
        race_name=race_name,
        race_date=race_date,
        venue=venue,
        race_number=race_number,
        race_time=race_time,
        prediction_result=prediction_result,
        predicted_at=datetime.now(),
        is_final=is_final,
    )

    return prediction_response


if __name__ == "__main__":
    # ロギング設定
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    import asyncio

    async def test_prediction():
        """予想生成のテスト"""
        # テスト用レースID（存在するレースIDに置き換える）
        test_race_id = "2024031005011112"

        try:
            prediction = await generate_prediction(
                race_id=test_race_id,
                is_final=False
            )

            print("\n予想結果（確率ベース・ランキング形式）:")
            print(f"予想ID: {prediction.prediction_id}")
            print(f"レース: {prediction.race_name}")
            print(f"予測信頼度: {prediction.prediction_result.prediction_confidence:.2%}")
            print(f"\n全馬ランキング:")
            for h in prediction.prediction_result.ranked_horses:
                print(f"  {h.rank}位: {h.horse_number}番 {h.horse_name} "
                      f"(勝率: {h.win_probability:.1%}, 複勝率: {h.place_probability:.1%})")

        except Exception as e:
            print(f"エラー: {e}")

    asyncio.run(test_prediction())
