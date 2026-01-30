"""
レース予想スケジューラ

開催前日に自動で：
1. 出馬表データの確認
2. 機械学習モデルで予想
3. 結果を保存/通知
"""

import argparse
import logging
from datetime import date, datetime, timedelta
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.db.connection import get_db
from src.models.feature_extractor import FastFeatureExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class RacePredictor:
    """レース予想クラス（ensemble_model対応 - 分類モデル+キャリブレーション+CatBoost）"""

    def __init__(
        self,
        model_path: str = "/app/models/ensemble_model_latest.pkl",
        use_adjustments: bool = True,
    ):
        self.model_path = model_path
        # 回帰モデル
        self.xgb_model = None
        self.lgb_model = None
        self.cb_model = None  # CatBoost追加
        # 分類モデル（新形式）
        self.xgb_win = None
        self.lgb_win = None
        self.cb_win = None  # CatBoost追加
        self.xgb_place = None
        self.lgb_place = None
        self.cb_place = None  # CatBoost追加
        # キャリブレーター（新形式）
        self.win_calibrator = None
        self.place_calibrator = None
        # 特徴量
        self.feature_names: list[str] | None = None
        self.has_classifiers = False
        self.has_catboost = False  # CatBoost有無フラグ
        # アンサンブル重み
        self.ensemble_weights: dict[str, float] | None = None
        # 特徴量調整係数
        self.feature_adjustments: dict[str, float] = {}
        self._load_model()
        if use_adjustments:
            self._load_feature_adjustments()

    def _load_model(self):
        """ensemble_modelを読み込み（新旧形式対応）"""
        try:
            model_data = joblib.load(self.model_path)
            version = model_data.get("version", "")
            models_dict = model_data.get("models", {})

            # 回帰モデル取得（複数形式に対応）
            if "xgb_regressor" in models_dict:
                # 新形式: v2_enhanced_ensemble
                self.xgb_model = models_dict["xgb_regressor"]
                self.lgb_model = models_dict.get("lgb_regressor")
            elif "xgb_model" in model_data:
                # 旧形式: weekly_retrain_model.py
                self.xgb_model = model_data["xgb_model"]
                self.lgb_model = model_data.get("lgb_model")
            elif "xgboost" in models_dict:
                # 旧形式: models.xgboost
                self.xgb_model = models_dict.get("xgboost")
                self.lgb_model = models_dict.get("lightgbm")
            else:
                raise ValueError("Invalid model format: ensemble_model required")

            # 分類モデル・キャリブレーター取得（新形式のみ）
            self.xgb_win = models_dict.get("xgb_win")
            self.lgb_win = models_dict.get("lgb_win")
            self.xgb_place = models_dict.get("xgb_place")
            self.lgb_place = models_dict.get("lgb_place")
            self.win_calibrator = models_dict.get("win_calibrator")
            self.place_calibrator = models_dict.get("place_calibrator")

            # CatBoostモデル取得（v5以降）
            self.cb_model = models_dict.get("cb_regressor")
            self.cb_win = models_dict.get("cb_win")
            self.cb_place = models_dict.get("cb_place")
            self.has_catboost = self.cb_model is not None

            # アンサンブル重み（デフォルト: XGB+LGB均等）
            self.ensemble_weights = model_data.get(
                "ensemble_weights", {"xgb": 0.5, "lgb": 0.5, "cb": 0.0}
            )

            self.has_classifiers = self.xgb_win is not None and self.lgb_win is not None

            self.feature_names = model_data.get("feature_names", [])
            logger.info(
                f"ensemble_model読み込み完了: {len(self.feature_names)}特徴量, "
                f"分類モデル={'あり' if self.has_classifiers else 'なし'}, "
                f"CatBoost={'あり' if self.has_catboost else 'なし'}, "
                f"version={version}"
            )
        except Exception as e:
            logger.error(f"モデル読み込み失敗: {e}")
            raise

    def _load_feature_adjustments(self):
        """特徴量調整係数をDBから読み込み"""
        try:
            from src.scheduler.shap_analyzer import ShapAnalyzer

            self.feature_adjustments = ShapAnalyzer.load_adjustments_from_db()
            if self.feature_adjustments:
                adjusted_count = sum(1 for v in self.feature_adjustments.values() if v != 1.0)
                logger.info(f"特徴量調整係数を適用: {adjusted_count}件の調整")
        except Exception as e:
            logger.warning(f"特徴量調整係数の読み込みに失敗（デフォルト使用）: {e}")
            self.feature_adjustments = {}

    def _apply_feature_adjustments(self, X: pd.DataFrame) -> pd.DataFrame:
        """特徴量に調整係数を適用"""
        if not self.feature_adjustments:
            return X

        X_adjusted = X.copy()
        for fname, adjustment in self.feature_adjustments.items():
            if fname in X_adjusted.columns and adjustment != 1.0:
                X_adjusted[fname] = X_adjusted[fname] * adjustment

        return X_adjusted

    def get_upcoming_races(self, target_date: date | None = None) -> list[dict]:
        """指定日の出馬表を取得"""
        if target_date is None:
            target_date = date.today() + timedelta(days=1)

        db = get_db()
        conn = db.get_connection()

        try:
            cur = conn.cursor()

            # 対象日のレースを取得
            kaisai_gappi = target_date.strftime("%m%d")
            kaisai_nen = str(target_date.year)

            # まず出馬表データがあるか確認
            # data_kubun: 1=登録, 2=速報, 3=枠順確定, 4=出馬表, 5=開催中, 6=確定前
            cur.execute(
                """
                SELECT DISTINCT r.race_code, r.keibajo_code, r.race_bango,
                       r.kyori, r.track_code, r.grade_code
                FROM race_shosai r
                WHERE r.kaisai_nen = %s
                  AND r.kaisai_gappi = %s
                  AND r.data_kubun IN ('1', '2', '3', '4', '5', '6')
                ORDER BY r.race_code
            """,
                (kaisai_nen, kaisai_gappi),
            )

            races = []
            keibajo_names = {
                "01": "札幌",
                "02": "函館",
                "03": "福島",
                "04": "新潟",
                "05": "東京",
                "06": "中山",
                "07": "中京",
                "08": "京都",
                "09": "阪神",
                "10": "小倉",
            }

            for row in cur.fetchall():
                races.append(
                    {
                        "race_code": row[0],
                        "keibajo_code": row[1],
                        "keibajo_name": keibajo_names.get(row[1], row[1]),
                        "race_bango": row[2],
                        "kyori": row[3],
                        "track_code": row[4],
                        "grade_code": row[5],
                    }
                )

            cur.close()
            return races

        finally:
            conn.close()

    def get_race_entries(self, race_code: str) -> list[dict]:
        """レースの出走馬情報を取得"""
        db = get_db()
        conn = db.get_connection()

        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    umaban, wakuban, ketto_toroku_bango, bamei,
                    kishu_code, futan_juryo, barei, seibetsu_code
                FROM umagoto_race_joho
                WHERE race_code = %s
                  AND data_kubun IN ('1', '2', '3', '4', '5', '6')
                ORDER BY umaban::int
            """,
                (race_code,),
            )

            entries = []
            for row in cur.fetchall():
                entries.append(
                    {
                        "umaban": row[0],
                        "wakuban": row[1],
                        "ketto_toroku_bango": row[2],
                        "bamei": row[3],
                        "kishu_code": row[4],
                        "futan_juryo": row[5],
                        "barei": row[6],
                        "seibetsu_code": row[7],
                    }
                )

            cur.close()
            return entries

        finally:
            conn.close()

    def predict_race(self, race_code: str) -> list[dict]:
        """レースの予想を実行"""
        db = get_db()
        conn = db.get_connection()

        try:
            # FastFeatureExtractorを使用
            extractor = FastFeatureExtractor(conn)

            # レース情報を取得
            cur = conn.cursor()
            cur.execute(
                """
                SELECT kaisai_nen, keibajo_code, race_bango
                FROM race_shosai
                WHERE race_code = %s
                LIMIT 1
            """,
                (race_code,),
            )
            race_info = cur.fetchone()
            if not race_info:
                return []

            year = int(race_info[0])

            # 特徴量抽出（1レース分）
            cur.execute(
                """
                SELECT race_code FROM race_shosai
                WHERE race_code = %s
            """,
                (race_code,),
            )

            # 出走馬データを取得
            cur.execute(
                """
                SELECT
                    race_code, umaban, wakuban, ketto_toroku_bango,
                    seibetsu_code, barei, futan_juryo,
                    blinker_shiyo_kubun, kishu_code, chokyoshi_code,
                    bataiju, zogen_sa, bamei
                FROM umagoto_race_joho
                WHERE race_code = %s
                  AND data_kubun IN ('1', '2', '3', '4', '5', '6')
                ORDER BY umaban::int
            """,
                (race_code,),
            )

            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            entries = [dict(zip(cols, row)) for row in rows]

            if not entries:
                logger.warning(f"出走馬データなし: {race_code}")
                return []

            # レース情報取得
            cur.execute(
                """
                SELECT race_code, kaisai_nen, kaisai_gappi, keibajo_code,
                       kyori, track_code, grade_code,
                       shiba_babajotai_code, dirt_babajotai_code
                FROM race_shosai
                WHERE race_code = %s
            """,
                (race_code,),
            )
            race_row = cur.fetchone()
            race_cols = [d[0] for d in cur.description]
            races = [dict(zip(race_cols, race_row))] if race_row else []

            # 過去成績を取得
            kettonums = [e["ketto_toroku_bango"] for e in entries if e.get("ketto_toroku_bango")]
            past_stats = extractor._get_past_stats_batch(kettonums)

            # 騎手・調教師キャッシュ
            extractor._cache_jockey_trainer_stats(year)

            # 追加データ
            jh_pairs = [
                (e.get("kishu_code", ""), e.get("ketto_toroku_bango", ""))
                for e in entries
                if e.get("kishu_code") and e.get("ketto_toroku_bango")
            ]
            jockey_horse_stats = extractor._get_jockey_horse_combo_batch(jh_pairs)
            surface_stats = extractor._get_surface_stats_batch(kettonums)
            turn_stats = extractor._get_turn_rates_batch(kettonums)
            for kettonum, stats in turn_stats.items():
                if kettonum in past_stats:
                    past_stats[kettonum]["right_turn_rate"] = stats["right_turn_rate"]
                    past_stats[kettonum]["left_turn_rate"] = stats["left_turn_rate"]
            training_stats = extractor._get_training_stats_batch(kettonums)

            # 特徴量生成
            features_list = []
            for entry in entries:
                # kakutei_chakujunがない場合はダミー値を設定
                entry["kakutei_chakujun"] = "01"  # 予測用ダミー

                features = extractor._build_features(
                    entry,
                    races,
                    past_stats,
                    jockey_horse_stats=jockey_horse_stats,
                    distance_stats=surface_stats,
                    training_stats=training_stats,
                )
                if features:
                    features["bamei"] = entry.get("bamei", "")
                    features_list.append(features)

            if not features_list:
                return []

            # 予測（ensemble: XGBoost + LightGBM + CatBoost の加重平均）
            df = pd.DataFrame(features_list)
            X = df[self.feature_names].fillna(0)

            # 特徴量調整係数を適用
            X = self._apply_feature_adjustments(X)

            # Model availability assertions for type checking
            assert self.xgb_model is not None, "XGBoost model not loaded"
            assert self.lgb_model is not None, "LightGBM model not loaded"
            assert self.ensemble_weights is not None, "Ensemble weights not loaded"

            # 回帰予測（着順スコア）
            xgb_pred = self.xgb_model.predict(X)
            lgb_pred = self.lgb_model.predict(X)

            # CatBoostがある場合は3モデルアンサンブル
            if self.has_catboost:
                cb_pred = self.cb_model.predict(X)
                w = self.ensemble_weights
                rank_scores = xgb_pred * w["xgb"] + lgb_pred * w["lgb"] + cb_pred * w["cb"]
            else:
                # 後方互換: XGB+LGBのみ
                w = self.ensemble_weights
                xgb_w = w.get("xgb", 0.5)
                lgb_w = w.get("lgb", 0.5)
                total = xgb_w + lgb_w
                rank_scores = (xgb_pred * xgb_w + lgb_pred * lgb_w) / total

            # 分類モデルによる確率予測
            if self.has_classifiers:
                assert self.xgb_win is not None, "XGBoost win classifier not loaded"
                assert self.lgb_win is not None, "LightGBM win classifier not loaded"
                # 勝利確率
                xgb_win_prob = self.xgb_win.predict_proba(X)[:, 1]
                lgb_win_prob = self.lgb_win.predict_proba(X)[:, 1]

                if self.has_catboost and self.cb_win is not None:
                    cb_win_prob = self.cb_win.predict_proba(X)[:, 1]
                    w = self.ensemble_weights
                    win_probs = (
                        xgb_win_prob * w["xgb"] + lgb_win_prob * w["lgb"] + cb_win_prob * w["cb"]
                    )
                else:
                    w = self.ensemble_weights
                    xgb_w = w.get("xgb", 0.5)
                    lgb_w = w.get("lgb", 0.5)
                    total = xgb_w + lgb_w
                    win_probs = (xgb_win_prob * xgb_w + lgb_win_prob * lgb_w) / total

                # 複勝確率
                assert self.xgb_place is not None, "XGBoost place classifier not loaded"
                assert self.lgb_place is not None, "LightGBM place classifier not loaded"
                xgb_place_prob = self.xgb_place.predict_proba(X)[:, 1]
                lgb_place_prob = self.lgb_place.predict_proba(X)[:, 1]

                if self.has_catboost and self.cb_place is not None:
                    cb_place_prob = self.cb_place.predict_proba(X)[:, 1]
                    w = self.ensemble_weights
                    place_probs = (
                        xgb_place_prob * w["xgb"]
                        + lgb_place_prob * w["lgb"]
                        + cb_place_prob * w["cb"]
                    )
                else:
                    w = self.ensemble_weights
                    xgb_w = w.get("xgb", 0.5)
                    lgb_w = w.get("lgb", 0.5)
                    total = xgb_w + lgb_w
                    place_probs = (xgb_place_prob * xgb_w + lgb_place_prob * lgb_w) / total

                # キャリブレーション適用
                if self.win_calibrator is not None:
                    win_probs = self.win_calibrator.predict(win_probs)
                if self.place_calibrator is not None:
                    place_probs = self.place_calibrator.predict(place_probs)

                # 正規化（勝率の合計を1に）
                win_sum = win_probs.sum()
                if win_sum > 0:
                    win_probs = win_probs / win_sum
            else:
                # 旧形式: スコアから確率を推定
                scores_exp = np.exp(-rank_scores)
                win_probs = scores_exp / scores_exp.sum()
                place_probs = None

            # 結果を整形
            results = []
            for i, score in enumerate(rank_scores):
                result = {
                    "umaban": features_list[i]["umaban"],
                    "bamei": features_list[i].get("bamei", ""),
                    "pred_score": float(score),
                    "win_prob": float(win_probs[i]),
                    "pred_rank": 0,  # 後で設定
                }
                if place_probs is not None:
                    result["place_prob"] = float(place_probs[i])
                results.append(result)

            # 予測順位を設定（スコアが低いほど上位）
            results.sort(key=lambda x: x["pred_score"])
            for i, r in enumerate(results):
                r["pred_rank"] = i + 1

            # 馬番順に戻す
            results.sort(key=lambda x: int(x["umaban"]))

            cur.close()
            return results

        finally:
            conn.close()

    def run_predictions(self, target_date: date | None = None) -> dict[str, Any]:
        """指定日の全レース予想を実行"""
        if target_date is None:
            target_date = date.today() + timedelta(days=1)

        logger.info(f"予想実行: {target_date}")

        # 出馬表確認
        races = self.get_upcoming_races(target_date)

        if not races:
            logger.info(f"{target_date}の出馬表データがありません")
            return {"date": str(target_date), "status": "no_data", "races": []}

        logger.info(f"{len(races)}レースの出馬表を確認")

        results: dict[str, Any] = {
            "date": str(target_date),
            "status": "success",
            "generated_at": datetime.now().isoformat(),
            "races": [],
        }

        for race in races:
            race_code = race["race_code"]
            logger.info(f"予想中: {race['keibajo_name']} {race['race_bango']}R")

            try:
                predictions = self.predict_race(race_code)

                if predictions:
                    # TOP3を抽出
                    top3 = sorted(predictions, key=lambda x: x["pred_rank"])[:3]

                    race_result = {
                        "race_code": race_code,
                        "keibajo": race["keibajo_name"],
                        "race_number": race["race_bango"],
                        "kyori": race["kyori"],
                        "predictions": predictions,
                        "top3": [
                            {
                                "rank": p["pred_rank"],
                                "umaban": p["umaban"],
                                "bamei": p["bamei"],
                                "win_prob": p.get("win_prob", 0),
                                "place_prob": p.get("place_prob"),
                            }
                            for p in top3
                        ],
                    }
                    results["races"].append(race_result)
                    top3_str = [
                        f"{p['umaban']}番{p['bamei']}({p.get('win_prob', 0)*100:.1f}%)"
                        for p in top3
                    ]
                    logger.info(f"  TOP3: {top3_str}")

            except Exception as e:
                logger.error(f"予想失敗 {race_code}: {e}")

        return results


def print_predictions(results: dict):
    """予想結果を表示"""
    print("\n" + "=" * 60)
    print(f"【{results['date']} レース予想】")
    print("=" * 60)

    if results["status"] == "no_data":
        print("出馬表データがありません")
        return

    for race in results["races"]:
        print(f"\n■ {race['keibajo']} {race['race_number']}R ({race['kyori']}m)")
        print("-" * 40)
        print("予想順位:")
        for p in race["top3"]:
            win_pct = p.get("win_prob", 0) * 100
            place_prob = p.get("place_prob")
            if place_prob is not None:
                place_pct = place_prob * 100
                print(
                    f"  {p['rank']}位: {p['umaban']}番 {p['bamei']} (勝率{win_pct:.1f}%, 複勝{place_pct:.1f}%)"
                )
            else:
                print(f"  {p['rank']}位: {p['umaban']}番 {p['bamei']} (勝率{win_pct:.1f}%)")

    print("\n" + "=" * 60)
    print(f"生成日時: {results['generated_at']}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="レース予想スケジューラ")
    parser.add_argument("--date", "-d", help="対象日 (YYYY-MM-DD)")
    parser.add_argument("--tomorrow", "-t", action="store_true", help="明日のレースを予想")
    parser.add_argument("--model", "-m", default="/app/models/ensemble_model_latest.pkl")

    args = parser.parse_args()

    # 対象日を決定
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    elif args.tomorrow:
        target_date = date.today() + timedelta(days=1)
    else:
        target_date = date.today() + timedelta(days=1)

    print(f"対象日: {target_date}")

    # 予想実行
    predictor = RacePredictor(args.model)
    results = predictor.run_predictions(target_date)

    # 結果表示
    print_predictions(results)


if __name__ == "__main__":
    main()
