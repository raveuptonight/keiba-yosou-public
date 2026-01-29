"""
SHAP分析モジュール

週末レースの予想結果を分析し、特徴量の寄与度を可視化する
- 的中/外れ別の特徴量重要度比較
- 過大評価/過小評価パターンの検出
- 週次分析レポート生成
"""

import json
import logging
from datetime import date, datetime, timedelta

import joblib
import numpy as np
import pandas as pd

try:
    import shap

    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False

from src.db.connection import get_db
from src.models.feature_extractor import FastFeatureExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class ShapAnalyzer:
    """SHAP値による予想分析"""

    def __init__(self, model_path: str = "/app/models/ensemble_model_latest.pkl"):
        self.model_path = model_path
        self.xgb_model = None
        self.lgb_model = None
        self.feature_names = None
        self.explainer = None
        self._load_model()

    def _load_model(self):
        """モデルを読み込み"""
        try:
            model_data = joblib.load(self.model_path)
            models_dict = model_data.get("models", {})

            # 回帰モデル取得
            if "xgb_regressor" in models_dict:
                self.xgb_model = models_dict["xgb_regressor"]
                self.lgb_model = models_dict.get("lgb_regressor")
            elif "xgb_model" in model_data:
                self.xgb_model = model_data["xgb_model"]
                self.lgb_model = model_data.get("lgb_model")
            elif "xgboost" in models_dict:
                self.xgb_model = models_dict.get("xgboost")
                self.lgb_model = models_dict.get("lightgbm")

            self.feature_names = model_data.get("feature_names", [])
            logger.info(f"モデル読み込み完了: {len(self.feature_names)}特徴量")

            # SHAP Explainerを初期化（XGBoostを使用）
            if SHAP_AVAILABLE and self.xgb_model is not None:
                self.explainer = shap.TreeExplainer(self.xgb_model)
                logger.info("SHAP TreeExplainer初期化完了")

        except Exception as e:
            logger.error(f"モデル読み込み失敗: {e}")
            raise

    def get_recent_race_dates(self, days_back: int = 7) -> list[date]:
        """直近のレース日（予想データがある日）を取得"""
        db = get_db()
        conn = db.get_connection()

        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT DISTINCT race_date
                FROM predictions
                WHERE race_date >= %s AND race_date < %s
                ORDER BY race_date DESC
            """,
                (date.today() - timedelta(days=days_back), date.today()),
            )

            dates = [row[0] for row in cur.fetchall()]
            cur.close()
            return dates
        finally:
            conn.close()

    def get_predictions_from_db(self, target_date: date) -> list[dict]:
        """DBから予想データを取得（レースごとに最新の予想のみ）"""
        db = get_db()
        conn = db.get_connection()

        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT DISTINCT ON (race_id)
                    prediction_id,
                    race_id,
                    race_date,
                    prediction_result,
                    predicted_at
                FROM predictions
                WHERE race_date = %s
                ORDER BY race_id, predicted_at DESC
            """,
                (target_date,),
            )

            predictions = []
            for row in cur.fetchall():
                prediction_result = row[3]
                if isinstance(prediction_result, str):
                    try:
                        prediction_result = json.loads(prediction_result)
                    except json.JSONDecodeError:
                        prediction_result = {}

                predictions.append(
                    {
                        "prediction_id": row[0],
                        "race_code": row[1],
                        "race_date": row[2],
                        "prediction_result": prediction_result,
                    }
                )

            cur.close()
            logger.info(f"予想データ取得: {len(predictions)}レース ({target_date})")
            return predictions

        finally:
            conn.close()

    def get_race_results(self, target_date: date) -> dict[str, dict]:
        """レース結果を取得"""
        db = get_db()
        conn = db.get_connection()

        try:
            cur = conn.cursor()
            kaisai_gappi = target_date.strftime("%m%d")
            kaisai_nen = str(target_date.year)

            cur.execute(
                """
                SELECT race_code, umaban, kakutei_chakujun, bamei
                FROM umagoto_race_joho
                WHERE race_code IN (
                    SELECT DISTINCT race_code
                    FROM race_shosai
                    WHERE kaisai_nen = %s AND kaisai_gappi = %s
                      AND data_kubun IN ('6', '7')
                )
                AND data_kubun IN ('6', '7')
                ORDER BY race_code, kakutei_chakujun::int
            """,
                (kaisai_nen, kaisai_gappi),
            )

            results = {}
            for row in cur.fetchall():
                race_code = row[0]
                if race_code not in results:
                    results[race_code] = {"horses": []}
                results[race_code]["horses"].append(
                    {
                        "umaban": row[1],
                        "chakujun": int(row[2]) if row[2] else 99,
                        "bamei": row[3],
                    }
                )

            cur.close()
            return results

        finally:
            conn.close()

    def extract_features_for_race(self, race_code: str) -> pd.DataFrame | None:
        """レースの特徴量を抽出"""
        db = get_db()
        conn = db.get_connection()

        try:
            extractor = FastFeatureExtractor(conn)
            cur = conn.cursor()

            # レース情報取得
            cur.execute(
                """
                SELECT kaisai_nen, race_code, kaisai_gappi, keibajo_code,
                       kyori, track_code, grade_code,
                       shiba_babajotai_code, dirt_babajotai_code
                FROM race_shosai
                WHERE race_code = %s
            """,
                (race_code,),
            )
            race_row = cur.fetchone()
            if not race_row:
                return None

            race_cols = [
                "kaisai_nen",
                "race_code",
                "kaisai_gappi",
                "keibajo_code",
                "kyori",
                "track_code",
                "grade_code",
                "shiba_babajotai_code",
                "dirt_babajotai_code",
            ]
            races = [dict(zip(race_cols, race_row))]
            year = int(race_row[0])

            # 出走馬データ取得
            cur.execute(
                """
                SELECT
                    race_code, umaban, wakuban, ketto_toroku_bango,
                    seibetsu_code, barei, futan_juryo,
                    blinker_shiyo_kubun, kishu_code, chokyoshi_code,
                    bataiju, zogen_sa, bamei, kakutei_chakujun
                FROM umagoto_race_joho
                WHERE race_code = %s
                  AND data_kubun IN ('6', '7')
                ORDER BY umaban::int
            """,
                (race_code,),
            )

            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            entries = [dict(zip(cols, row)) for row in rows]

            if not entries:
                return None

            # 過去成績取得
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
                    features["actual_chakujun"] = int(entry.get("kakutei_chakujun", 99))
                    features_list.append(features)

            cur.close()

            if not features_list:
                return None

            return pd.DataFrame(features_list)

        except Exception as e:
            logger.error(f"特徴量抽出エラー ({race_code}): {e}")
            return None
        finally:
            conn.close()

    def calculate_shap_values(self, X: pd.DataFrame) -> np.ndarray:
        """SHAP値を計算"""
        if not SHAP_AVAILABLE:
            logger.warning("SHAPライブラリが利用できません")
            return None

        if self.explainer is None:
            logger.warning("SHAP Explainerが初期化されていません")
            return None

        try:
            shap_values = self.explainer.shap_values(X)
            return shap_values
        except Exception as e:
            logger.error(f"SHAP値計算エラー: {e}")
            return None

    def analyze_race(self, race_code: str, prediction: dict) -> dict | None:
        """1レースを分析（EV推奨・軸馬形式）"""
        # 特徴量抽出
        df = self.extract_features_for_race(race_code)
        if df is None or df.empty:
            return None

        # 予想結果から馬を取得
        ranked_horses = prediction.get("prediction_result", {}).get("ranked_horses", [])
        if not ranked_horses:
            return None

        # EV推奨馬を特定（EV >= 1.5）
        ev_recommended = []
        for h in ranked_horses:
            win_prob = h.get("win_probability", 0)
            odds = h.get("predicted_odds", 0)
            if odds > 0 and win_prob > 0:
                win_ev = win_prob * odds
                if win_ev >= 1.5:
                    ev_recommended.append(h)

        # 軸馬を特定（複勝確率最高）
        axis_horse = (
            max(ranked_horses, key=lambda h: h.get("place_probability", 0))
            if ranked_horses
            else None
        )

        # 特徴量のみ抽出
        X = df[self.feature_names].fillna(0)

        # SHAP値計算
        shap_values = self.calculate_shap_values(X)
        if shap_values is None:
            return None

        # 軸馬の分析
        axis_umaban = str(axis_horse.get("horse_number", "")).zfill(2) if axis_horse else None
        axis_analysis = None
        if axis_umaban:
            horse_row = df[df["umaban"].astype(str).str.zfill(2) == axis_umaban]
            if not horse_row.empty:
                actual_chakujun = int(horse_row["actual_chakujun"].iloc[0])
                horse_idx = horse_row.index[0]
                horse_shap = shap_values[horse_idx]
                axis_contributions = {
                    fname: float(horse_shap[i]) for i, fname in enumerate(self.feature_names)
                }
                axis_analysis = {
                    "umaban": axis_umaban,
                    "bamei": axis_horse.get("horse_name", ""),
                    "actual_chakujun": actual_chakujun,
                    "is_place": actual_chakujun <= 3,
                    "place_prob": axis_horse.get("place_probability", 0),
                    "feature_contributions": axis_contributions,
                }

        # EV推奨馬の分析
        ev_analyses = []
        for h in ev_recommended:
            h_umaban = str(h.get("horse_number", "")).zfill(2)
            horse_row = df[df["umaban"].astype(str).str.zfill(2) == h_umaban]
            if not horse_row.empty:
                actual_chakujun = int(horse_row["actual_chakujun"].iloc[0])
                horse_idx = horse_row.index[0]
                horse_shap = shap_values[horse_idx]
                ev_contributions = {
                    fname: float(horse_shap[i]) for i, fname in enumerate(self.feature_names)
                }
                win_prob = h.get("win_probability", 0)
                odds = h.get("predicted_odds", 0)
                ev_analyses.append(
                    {
                        "umaban": h_umaban,
                        "bamei": h.get("horse_name", ""),
                        "actual_chakujun": actual_chakujun,
                        "is_hit": actual_chakujun == 1,
                        "is_place": actual_chakujun <= 3,
                        "win_ev": win_prob * odds,
                        "win_prob": win_prob,
                        "feature_contributions": ev_contributions,
                    }
                )

        return {
            "race_code": race_code,
            "axis_analysis": axis_analysis,
            "ev_analyses": ev_analyses,
            "has_ev_rec": len(ev_recommended) > 0,
        }

    def analyze_dates(self, target_dates: list[date]) -> dict:
        """複数日のレースを分析（EV推奨・軸馬形式）"""
        all_analyses = []

        for target_date in target_dates:
            predictions = self.get_predictions_from_db(target_date)

            for pred in predictions:
                race_code = pred["race_code"]
                analysis = self.analyze_race(race_code, pred)
                if analysis:
                    analysis["date"] = str(target_date)
                    all_analyses.append(analysis)

        if not all_analyses:
            return {"status": "no_data", "analyses": []}

        first_date = min(target_dates)
        last_date = max(target_dates)

        # 軸馬の的中/外れで分類
        axis_places = [
            a for a in all_analyses if a.get("axis_analysis") and a["axis_analysis"].get("is_place")
        ]
        axis_misses = [
            a
            for a in all_analyses
            if a.get("axis_analysis") and not a["axis_analysis"].get("is_place")
        ]

        # EV推奨馬の的中/外れで分類
        ev_hits = []
        ev_misses = []
        for a in all_analyses:
            for ev in a.get("ev_analyses", []):
                if ev.get("is_hit"):
                    ev_hits.append({"feature_contributions": ev["feature_contributions"]})
                elif not ev.get("is_place"):
                    ev_misses.append({"feature_contributions": ev["feature_contributions"]})

        # 軸馬の特徴量寄与度を集計
        axis_place_contributions = self._aggregate_contributions(
            [
                {"feature_contributions": a["axis_analysis"]["feature_contributions"]}
                for a in axis_places
            ]
        )
        axis_miss_contributions = self._aggregate_contributions(
            [
                {"feature_contributions": a["axis_analysis"]["feature_contributions"]}
                for a in axis_misses
            ]
        )

        # EV推奨馬の特徴量寄与度を集計
        ev_hit_contributions = self._aggregate_contributions(ev_hits)
        ev_miss_contributions = self._aggregate_contributions(ev_misses)

        # 差分を計算（的中時 - 外れ時）
        axis_diff = {}
        all_features = set(axis_place_contributions.keys()) | set(axis_miss_contributions.keys())
        for fname in all_features:
            place_val = axis_place_contributions.get(fname, 0)
            miss_val = axis_miss_contributions.get(fname, 0)
            axis_diff[fname] = place_val - miss_val

        ev_diff = {}
        all_features = set(ev_hit_contributions.keys()) | set(ev_miss_contributions.keys())
        for fname in all_features:
            hit_val = ev_hit_contributions.get(fname, 0)
            miss_val = ev_miss_contributions.get(fname, 0)
            ev_diff[fname] = hit_val - miss_val

        # 重要な差分をソート
        sorted_axis_diff = sorted(axis_diff.items(), key=lambda x: abs(x[1]), reverse=True)
        sorted_ev_diff = sorted(ev_diff.items(), key=lambda x: abs(x[1]), reverse=True)

        # EV推奨馬の成績集計
        total_ev_count = sum(len(a.get("ev_analyses", [])) for a in all_analyses)
        ev_tansho_hits = sum(
            1 for a in all_analyses for ev in a.get("ev_analyses", []) if ev.get("is_hit")
        )
        ev_fukusho_hits = sum(
            1 for a in all_analyses for ev in a.get("ev_analyses", []) if ev.get("is_place")
        )

        return {
            "status": "success",
            "period": f"{first_date} - {last_date}",
            "total_races": len(all_analyses),
            # 軸馬成績
            "axis_place_count": len(axis_places),
            "axis_miss_count": len(axis_misses),
            "axis_place_rate": len(axis_places) / len(all_analyses) * 100 if all_analyses else 0,
            "axis_place_contributions": axis_place_contributions,
            "axis_miss_contributions": axis_miss_contributions,
            "axis_diff_contributions": dict(sorted_axis_diff[:20]),
            # EV推奨成績
            "ev_rec_count": total_ev_count,
            "ev_tansho_hits": ev_tansho_hits,
            "ev_fukusho_hits": ev_fukusho_hits,
            "ev_tansho_rate": ev_tansho_hits / total_ev_count * 100 if total_ev_count > 0 else 0,
            "ev_fukusho_rate": ev_fukusho_hits / total_ev_count * 100 if total_ev_count > 0 else 0,
            "ev_hit_contributions": ev_hit_contributions,
            "ev_miss_contributions": ev_miss_contributions,
            "ev_diff_contributions": dict(sorted_ev_diff[:20]),
            "analyses": all_analyses,
        }

    def analyze_weekend(self, saturday: date, sunday: date) -> dict:
        """週末のレースを分析（後方互換性のためのラッパー）"""
        return self.analyze_dates([saturday, sunday])

    def calculate_feature_adjustments(
        self, analysis: dict, threshold: float = 0.1
    ) -> dict[str, float]:
        """
        SHAP分析結果から特徴量調整係数を計算

        Args:
            analysis: analyze_dates()の結果
            threshold: 調整対象とする差分の閾値

        Returns:
            特徴量名 → 調整係数（1.0が基準、<1.0は抑制、>1.0は強化）
        """
        if analysis.get("status") != "success":
            return {}

        diff = analysis.get("diff_contributions", {})
        analysis.get("hit_contributions", {})
        analysis.get("miss_contributions", {})

        adjustments = {}

        for fname in self.feature_names:
            diff_val = diff.get(fname, 0)

            # 差分が閾値以上の場合のみ調整
            if abs(diff_val) < threshold:
                adjustments[fname] = 1.0
                continue

            # 外れ時に高い（diff < 0）→ 抑制（係数 < 1.0）
            # 的中時に高い（diff > 0）→ 強化（係数 > 1.0）
            # スケール: diff_val * 0.5 で最大±50%調整
            adjustment = 1.0 + (diff_val * 0.5)

            # 0.5〜1.5の範囲に制限
            adjustment = max(0.5, min(1.5, adjustment))
            adjustments[fname] = round(adjustment, 4)

        return adjustments

    def save_adjustments_to_db(
        self, adjustments: dict[str, float], analysis_date: date = None
    ) -> bool:
        """特徴量調整係数をDBに保存"""
        if not adjustments:
            return False

        if analysis_date is None:
            analysis_date = date.today()

        db = get_db()
        conn = db.get_connection()

        try:
            cur = conn.cursor()

            # feature_adjustmentsテーブルに保存
            cur.execute(
                """
                INSERT INTO feature_adjustments (
                    adjustment_date, adjustments, is_active, created_at
                ) VALUES (%s, %s, TRUE, CURRENT_TIMESTAMP)
                ON CONFLICT (adjustment_date) DO UPDATE SET
                    adjustments = EXCLUDED.adjustments,
                    is_active = TRUE,
                    created_at = CURRENT_TIMESTAMP
            """,
                (analysis_date, json.dumps(adjustments)),
            )

            # 古い調整係数を非アクティブ化（直近3件のみアクティブ）
            cur.execute(
                """
                UPDATE feature_adjustments
                SET is_active = FALSE
                WHERE adjustment_date NOT IN (
                    SELECT adjustment_date FROM feature_adjustments
                    ORDER BY adjustment_date DESC LIMIT 3
                )
            """
            )

            conn.commit()
            logger.info(f"特徴量調整係数をDBに保存: {len(adjustments)}件")
            return True

        except Exception as e:
            logger.error(f"特徴量調整係数保存エラー: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    @staticmethod
    def load_adjustments_from_db() -> dict[str, float]:
        """最新の特徴量調整係数をDBから読み込み"""
        db = get_db()
        conn = db.get_connection()

        try:
            cur = conn.cursor()

            # 最新のアクティブな調整係数を取得
            cur.execute(
                """
                SELECT adjustments FROM feature_adjustments
                WHERE is_active = TRUE
                ORDER BY adjustment_date DESC
                LIMIT 1
            """
            )

            row = cur.fetchone()
            cur.close()

            if row and row[0]:
                adjustments = row[0]
                if isinstance(adjustments, str):
                    adjustments = json.loads(adjustments)
                logger.info(f"特徴量調整係数を読み込み: {len(adjustments)}件")
                return adjustments

            return {}

        except Exception as e:
            logger.error(f"特徴量調整係数読み込みエラー: {e}")
            return {}
        finally:
            if conn:
                conn.close()

    def _aggregate_contributions(self, analyses: list[dict]) -> dict[str, float]:
        """特徴量寄与度を集計"""
        if not analyses:
            return {}

        aggregated = {}
        for analysis in analyses:
            for fname, value in analysis.get("feature_contributions", {}).items():
                if fname not in aggregated:
                    aggregated[fname] = []
                aggregated[fname].append(value)

        # 平均を計算
        return {fname: np.mean(values) for fname, values in aggregated.items()}

    def generate_report(self, analysis: dict) -> str:
        """分析レポートを生成（EV推奨・軸馬形式）"""
        if analysis.get("status") != "success":
            return "分析データがありません"

        lines = [
            "📊 **SHAP特徴量分析レポート**",
            f"期間: {analysis['period']}",
            f"分析レース数: {analysis['total_races']}R",
            "",
        ]

        # 軸馬成績
        lines.append("**【軸馬成績】** (複勝確率1位)")
        axis_place = analysis.get("axis_place_count", 0)
        axis_total = axis_place + analysis.get("axis_miss_count", 0)
        lines.append(
            f"  複勝的中: {axis_place}/{axis_total}R ({analysis.get('axis_place_rate', 0):.1f}%)"
        )

        # 軸馬の特徴量差分
        axis_diff = analysis.get("axis_diff_contributions", {})
        if axis_diff:
            lines.append("")
            lines.append("**【軸馬: 複勝的中/外れで差が大きい特徴量】**")
            lines.append("(正: 的中時に高い、負: 外れ時に高い)")
            for i, (fname, value) in enumerate(list(axis_diff.items())[:7]):
                sign = "+" if value > 0 else ""
                lines.append(f"  {i+1}. {fname}: {sign}{value:.4f}")

        # EV推奨成績
        lines.append("")
        ev_count = analysis.get("ev_rec_count", 0)
        if ev_count > 0:
            lines.append("**【EV推奨成績】** (EV >= 1.5)")
            lines.append(f"  推奨馬数: {ev_count}頭")
            lines.append(
                f"  単勝的中: {analysis.get('ev_tansho_hits', 0)} ({analysis.get('ev_tansho_rate', 0):.1f}%)"
            )
            lines.append(
                f"  複勝的中: {analysis.get('ev_fukusho_hits', 0)} ({analysis.get('ev_fukusho_rate', 0):.1f}%)"
            )

            # EV推奨の特徴量差分
            ev_diff = analysis.get("ev_diff_contributions", {})
            if ev_diff:
                lines.append("")
                lines.append("**【EV推奨: 的中/外れで差が大きい特徴量】**")
                for i, (fname, value) in enumerate(list(ev_diff.items())[:7]):
                    sign = "+" if value > 0 else ""
                    lines.append(f"  {i+1}. {fname}: {sign}{value:.4f}")
        else:
            lines.append("**【EV推奨成績】**")
            lines.append("  EV推奨なし")

        return "\n".join(lines)

    def send_discord_notification(self, report: str):
        """Discord通知を送信"""
        import os

        import requests

        bot_token = os.getenv("DISCORD_BOT_TOKEN")
        channel_id = os.getenv("DISCORD_NOTIFICATION_CHANNEL_ID")

        if not bot_token or not channel_id:
            logger.warning("Discord通知設定がありません")
            return

        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"}

        try:
            # 2000文字制限対応
            if len(report) > 1900:
                report = report[:1900] + "\n..."

            response = requests.post(url, headers=headers, json={"content": report}, timeout=10)
            if response.status_code in (200, 201):
                logger.info("SHAP分析Discord通知送信完了")
            else:
                logger.warning(f"Discord通知失敗: {response.status_code}")
        except Exception as e:
            logger.error(f"Discord通知エラー: {e}")

    def save_analysis_to_db(self, analysis: dict) -> bool:
        """分析結果をDBに保存"""
        if analysis.get("status") != "success":
            return False

        db = get_db()
        conn = db.get_connection()

        try:
            cur = conn.cursor()

            # shap_analysisテーブルに保存
            cur.execute(
                """
                INSERT INTO shap_analysis (
                    analysis_date, period_start, period_end,
                    total_races, hit_count, place_count, miss_count,
                    hit_rate, place_rate,
                    hit_contributions, miss_contributions, diff_contributions,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (analysis_date) DO UPDATE SET
                    total_races = EXCLUDED.total_races,
                    hit_count = EXCLUDED.hit_count,
                    place_count = EXCLUDED.place_count,
                    miss_count = EXCLUDED.miss_count,
                    hit_rate = EXCLUDED.hit_rate,
                    place_rate = EXCLUDED.place_rate,
                    hit_contributions = EXCLUDED.hit_contributions,
                    miss_contributions = EXCLUDED.miss_contributions,
                    diff_contributions = EXCLUDED.diff_contributions,
                    created_at = CURRENT_TIMESTAMP
            """,
                (
                    date.today(),
                    analysis["period"].split(" - ")[0],
                    analysis["period"].split(" - ")[1],
                    analysis["total_races"],
                    analysis["hit_count"],
                    analysis["place_count"],
                    analysis["miss_count"],
                    analysis["hit_rate"],
                    analysis["place_rate"],
                    json.dumps(analysis.get("hit_contributions", {})),
                    json.dumps(analysis.get("miss_contributions", {})),
                    json.dumps(analysis.get("diff_contributions", {})),
                ),
            )

            conn.commit()
            logger.info("SHAP分析結果をDBに保存")
            return True

        except Exception as e:
            logger.error(f"SHAP分析DB保存エラー: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()


def analyze_last_weekend():
    """先週末の分析を実行（予想データがある日を自動検出）"""
    if not SHAP_AVAILABLE:
        logger.error("SHAPライブラリがインストールされていません")
        print("SHAPライブラリをインストールしてください: pip install shap")
        return

    analyzer = ShapAnalyzer()

    # 予想データがある直近の日を取得（最大7日前まで）
    race_dates = analyzer.get_recent_race_dates(days_back=7)

    if not race_dates:
        print("直近7日間に予想データがありません")
        return

    # 直近2日分を分析対象とする
    target_dates = sorted(race_dates)[-2:] if len(race_dates) >= 2 else race_dates
    first_date = target_dates[0]
    last_date = target_dates[-1]

    print(f"\n=== SHAP特徴量分析 ({first_date} - {last_date}) ===\n")
    print(f"対象日: {', '.join(str(d) for d in target_dates)}")

    analysis = analyzer.analyze_dates(target_dates)

    if analysis["status"] == "success":
        # レポート生成
        report = analyzer.generate_report(analysis)
        print(report)

        # Discord通知
        analyzer.send_discord_notification(report)

        # DB保存
        analyzer.save_analysis_to_db(analysis)
    else:
        print("分析データがありません")


def main():
    """メイン実行"""
    import argparse

    parser = argparse.ArgumentParser(description="SHAP特徴量分析")
    parser.add_argument("--date", "-d", help="分析日 (YYYY-MM-DD)")
    parser.add_argument("--weekend", "-w", action="store_true", help="先週末を分析")

    args = parser.parse_args()

    if args.weekend or not args.date:
        analyze_last_weekend()
    else:
        # 特定日の分析
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        print(f"\n=== SHAP特徴量分析 ({target_date}) ===\n")

        analyzer = ShapAnalyzer()
        predictions = analyzer.get_predictions_from_db(target_date)

        analyses = []
        for pred in predictions:
            race_code = pred["race_code"]
            analysis = analyzer.analyze_race(race_code, pred)
            if analysis:
                analysis["date"] = str(target_date)
                analyses.append(analysis)

        if analyses:
            # 簡易レポート
            hits = [a for a in analyses if a["is_hit"]]
            places = [a for a in analyses if a["is_place"]]
            print(f"分析レース数: {len(analyses)}")
            print(f"単勝的中: {len(hits)}R ({len(hits)/len(analyses)*100:.1f}%)")
            print(f"複勝圏: {len(places)}R ({len(places)/len(analyses)*100:.1f}%)")
        else:
            print("分析データがありません")


if __name__ == "__main__":
    main()
