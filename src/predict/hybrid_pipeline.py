"""
ハイブリッド予想パイプライン

機械学習（XGBoost） + LLM（Gemini）による高精度予想システム

Phase 0: 特徴量抽出 + ML予測
Phase 1: LLMデータ分析（MLスコア考慮）
Phase 2: LLM最終予想（ハイブリッド）
"""

import json
import logging
import pandas as pd
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from src.features.feature_pipeline import FeatureExtractor
from src.features.real_feature_extractor import RealFeatureExtractor
from src.models.xgboost_model import HorseRacingXGBoost
from src.db.connection import get_db
from src.predict.llm import LLMClient
from src.db.predictions_db import PredictionsDB
from src.config import (
    PROMPT_ML_TOP_HORSES_PHASE1,
    PROMPT_ML_TOP_HORSES_PHASE2,
    PROMPT_LEARNING_POINTS_LIMIT,
    PROMPT_LEARNING_POINTS_PER_RACE,
    PROMPT_LEARNING_POINTS_DAYS_BACK,
    LLM_ANALYSIS_TEMPERATURE,
    LLM_PREDICTION_TEMPERATURE,
)
from src.exceptions import (
    PipelineError,
    FeatureExtractionError,
    PredictionError,
    AnalysisError,
    LLMError,
    ModelPredictionError,
    DatabaseError,
    DataParseError,
)

# ロガー設定
logger = logging.getLogger(__name__)


class HybridPredictionPipeline:
    """
    機械学習 + LLM ハイブリッド予想パイプライン

    このクラスは3段階の予想プロセスを管理します：
    1. Phase 0: 特徴量抽出 & ML予測
    2. Phase 1: LLMデータ分析
    3. Phase 2: LLM最終予想

    Attributes:
        feature_extractor: 特徴量抽出器
        ml_model: XGBoostモデル
        llm_client: LLMクライアント
        predictions_db: 予想結果DBクライアント
    """

    def __init__(self, model_path: Optional[str] = None, use_real_features: bool = True):
        """
        Args:
            model_path: 学習済みモデルのパス（省略時はモックモード）
            use_real_features: 実データから特徴量を抽出するか（False=モックデータ）

        Raises:
            ModelLoadError: モデル読み込みに失敗した場合
        """
        try:
            self.use_real_features = use_real_features
            self.feature_extractor = FeatureExtractor()
            self.real_feature_extractor = None  # 必要時に初期化
            self.ml_model = HorseRacingXGBoost()
            self.llm_client = LLMClient()
            self.predictions_db = PredictionsDB()

            # モデル読み込み（存在する場合）
            if model_path:
                logger.info(f"モデル読み込み: {model_path}")
                self.ml_model.load(model_path)

            logger.info(f"パイプライン初期化完了: use_real_features={use_real_features}")
        except Exception as e:
            logger.error(f"パイプライン初期化失敗: {e}")
            raise PipelineError(f"パイプライン初期化失敗: {e}") from e

    def predict(
        self,
        race_id: str,
        race_data: Dict[str, Any],
        race_date: Optional[str] = None,
        phase: str = "all",
        temperature: Optional[float] = None,
        save_to_db: bool = True
    ) -> Dict[str, Any]:
        """
        ハイブリッド予想実行

        Args:
            race_id: レースID
            race_data: レースデータ（race_name, date, venue, distance, track_condition, horses含む）
            race_date: レース日付（YYYY-MM-DD形式、省略時は今日）
            phase: 実行フェーズ（'analyze', 'predict', 'all'）
            temperature: LLM温度パラメータ（省略時は設定値）
            save_to_db: DBに保存するか

        Returns:
            予想結果（以下のキーを含む）:
                - race_id: レースID
                - race_date: レース日付
                - timestamp: 予想時刻
                - ml_scores: ML予測結果
                - analysis: Phase 1分析結果（phase='analyze'/'all'の場合）
                - prediction: Phase 2予想結果（phase='predict'/'all'の場合）
                - prediction_id: DB保存ID（save_to_db=Trueの場合）

        Raises:
            PipelineError: パイプライン実行に失敗した場合
            FeatureExtractionError: 特徴量抽出に失敗した場合
            ModelPredictionError: ML予測に失敗した場合
            AnalysisError: LLM分析に失敗した場合
            PredictionError: LLM予想に失敗した場合
        """
        # デフォルト値設定
        if race_date is None:
            race_date = datetime.now().strftime('%Y-%m-%d')

        result: Dict[str, Any] = {
            'race_id': race_id,
            'race_date': race_date,
            'timestamp': datetime.now().isoformat()
        }

        try:
            # Phase 0: 特徴量生成 & ML予測
            logger.info(f"[Phase 0] 特徴量生成 & ML予測開始: {race_id}")
            print("\n[Phase 0] 特徴量生成 & 機械学習予測")
            ml_scores = self._run_ml_prediction(race_id, race_data)
            result['ml_scores'] = ml_scores
            logger.info(f"[Phase 0] 完了: {len(ml_scores)}頭の予測")

            # Phase 1: LLMデータ分析
            if phase in ("analyze", "all"):
                logger.info("[Phase 1] LLMデータ分析開始")
                print("\n[Phase 1] データ分析（ML + LLM）")
                analysis = self._run_phase1(
                    race_data,
                    ml_scores,
                    temperature or LLM_ANALYSIS_TEMPERATURE
                )
                result['analysis'] = analysis
                logger.info("[Phase 1] 完了")

            # Phase 2: LLM最終予想
            if phase in ("predict", "all"):
                logger.info("[Phase 2] LLM最終予想開始")
                print("\n[Phase 2] 予想生成（ハイブリッド）")
                prediction = self._run_phase2(
                    race_data,
                    ml_scores,
                    result.get('analysis', {}),
                    temperature or LLM_PREDICTION_TEMPERATURE
                )
                result['prediction'] = prediction
                logger.info("[Phase 2] 完了")

            # データベースに保存
            if save_to_db and phase == "all":
                try:
                    prediction_id = self.predictions_db.save_prediction(
                        race_id=race_id,
                        race_date=race_date,
                        ml_scores=ml_scores,
                        analysis=result.get('analysis', {}),
                        prediction=result.get('prediction', {}),
                        model_version="v1.0"
                    )
                    result['prediction_id'] = prediction_id
                    logger.info(f"予想結果保存成功: prediction_id={prediction_id}")
                    print(f"\n✅ 予想結果保存: prediction_id={prediction_id}")
                except DatabaseError as e:
                    logger.error(f"予想結果保存失敗: {e}")
                    print(f"\n⚠️  予想結果保存失敗: {e}")
                    # DB保存失敗は致命的でないため、処理続行

            logger.info(f"予想パイプライン完了: {race_id}")
            return result

        except (FeatureExtractionError, ModelPredictionError, AnalysisError, PredictionError) as e:
            # 既知のエラーは再スロー
            logger.error(f"予想パイプライン失敗: {e}")
            raise
        except Exception as e:
            # 予期しないエラー
            logger.exception(f"予想パイプライン予期しないエラー: {e}")
            raise PipelineError(f"予想パイプライン失敗: {e}") from e

    def _run_ml_prediction(
        self,
        race_id: str,
        race_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        機械学習予測

        Args:
            race_id: レースID
            race_data: レースデータ

        Returns:
            MLスコア結果（horse_number, horse_name, rank_score, win_probability, features含む）

        Raises:
            FeatureExtractionError: 特徴量抽出に失敗した場合
            ModelPredictionError: ML予測に失敗した場合
        """
        try:
            num_horses = len(race_data.get('horses', []))
            if num_horses == 0:
                raise FeatureExtractionError("出走馬が0頭です")

            # 特徴量抽出（実データ or モック）
            logger.debug(f"特徴量抽出開始: {num_horses}頭, use_real={self.use_real_features}")

            if self.use_real_features:
                # 実データから特徴量抽出
                features_df = self._extract_real_features(race_id, race_data)
            else:
                # モックデータ
                features_df = self.feature_extractor.extract_all_features(
                    race_id,
                    num_horses
                )

            if features_df.empty:
                logger.warning("特徴量抽出結果が空、モックにフォールバック")
                features_df = self.feature_extractor.extract_all_features(
                    race_id,
                    num_horses
                )

            # ML予測
            logger.debug("ML予測開始")
            rank_scores = self.ml_model.predict(features_df)
            win_probs = self.ml_model.predict_win_probability(features_df)

            # 結果をリストに変換
            results: List[Dict[str, Any]] = []
            for i, horse in enumerate(race_data.get('horses', [])):
                results.append({
                    'horse_number': horse.get('number', i + 1),
                    'horse_name': horse.get('name', f'Horse {i + 1}'),
                    'rank_score': float(rank_scores[i]),
                    'win_probability': float(win_probs[i]),
                    'features': features_df.iloc[i].to_dict() if i < len(features_df) else {}
                })

            # 着順スコアでソート
            results.sort(key=lambda x: x['rank_score'])

            # 順位を付与
            for rank, item in enumerate(results, 1):
                item['ml_predicted_rank'] = rank

            return results

        except Exception as e:
            logger.error(f"ML予測失敗: {e}")
            if isinstance(e, (FeatureExtractionError, ModelPredictionError)):
                raise
            raise ModelPredictionError(f"ML予測失敗: {e}") from e

    def _extract_real_features(
        self,
        race_id: str,
        race_data: Dict[str, Any]
    ) -> pd.DataFrame:
        """
        実データベースから特徴量を抽出

        Args:
            race_id: レースID（16桁のrace_code）
            race_data: レースデータ

        Returns:
            DataFrame: 特徴量
        """
        try:
            # DB接続を取得
            db = get_db()
            conn = db.get_connection()

            if not conn:
                logger.warning("DB接続失敗、モックにフォールバック")
                return pd.DataFrame()

            try:
                # RealFeatureExtractorで特徴量抽出
                if self.real_feature_extractor is None:
                    self.real_feature_extractor = RealFeatureExtractor(conn)
                else:
                    self.real_feature_extractor.conn = conn

                # data_kubun: 出馬表段階では "4" or "5"、確定後は "7"
                # 予想時はまだ確定前なので "5"（速報出馬表）を使用
                features_list = self.real_feature_extractor.extract_features_for_race(
                    race_id,
                    data_kubun="5"
                )

                if not features_list:
                    # 確定データでも試す
                    features_list = self.real_feature_extractor.extract_features_for_race(
                        race_id,
                        data_kubun="7"
                    )

                if not features_list:
                    logger.warning(f"特徴量抽出結果が空: race_id={race_id}")
                    return pd.DataFrame()

                # umabanでソートしてDataFrameに変換
                features_list.sort(key=lambda x: x.get('umaban', 0))
                df = pd.DataFrame(features_list)

                logger.info(f"実特徴量抽出完了: {len(df)}頭, features={len(df.columns)}")
                return df

            finally:
                conn.close()

        except Exception as e:
            logger.error(f"実特徴量抽出失敗: {e}")
            return pd.DataFrame()

    def _run_phase1(
        self,
        race_data: Dict[str, Any],
        ml_scores: List[Dict[str, Any]],
        temperature: float
    ) -> Dict[str, Any]:
        """
        Phase 1: データ分析（ML + LLM）

        Args:
            race_data: レースデータ
            ml_scores: MLスコア
            temperature: LLM温度

        Returns:
            分析結果

        Raises:
            AnalysisError: 分析に失敗した場合
        """
        try:
            # プロンプト生成
            prompt = self._build_phase1_prompt(race_data, ml_scores)

            # LLM実行
            logger.debug("LLM分析開始")
            response = self.llm_client.generate(
                prompt=prompt,
                temperature=temperature
            )

            # JSON解析
            try:
                return json.loads(response)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON解析失敗、raw_responseとして返却: {e}")
                # JSON解析失敗時はテキストとして返す
                return {'raw_response': response}

        except LLMError as e:
            logger.error(f"LLM分析失敗: {e}")
            raise AnalysisError(f"LLM分析失敗: {e}") from e
        except Exception as e:
            logger.error(f"Phase 1予期しないエラー: {e}")
            raise AnalysisError(f"Phase 1失敗: {e}") from e

    def _run_phase2(
        self,
        race_data: Dict[str, Any],
        ml_scores: List[Dict[str, Any]],
        analysis: Dict[str, Any],
        temperature: float
    ) -> Dict[str, Any]:
        """
        Phase 2: 予想生成（ハイブリッド）

        Args:
            race_data: レースデータ
            ml_scores: MLスコア
            analysis: Phase1分析結果
            temperature: LLM温度

        Returns:
            予想結果

        Raises:
            PredictionError: 予想生成に失敗した場合
        """
        try:
            # プロンプト生成
            prompt = self._build_phase2_prompt(race_data, ml_scores, analysis)

            # LLM実行
            logger.debug("LLM予想生成開始")
            response = self.llm_client.generate(
                prompt=prompt,
                temperature=temperature
            )

            # JSON解析
            try:
                return json.loads(response)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON解析失敗、raw_responseとして返却: {e}")
                return {'raw_response': response}

        except LLMError as e:
            logger.error(f"LLM予想生成失敗: {e}")
            raise PredictionError(f"LLM予想生成失敗: {e}") from e
        except Exception as e:
            logger.error(f"Phase 2予期しないエラー: {e}")
            raise PredictionError(f"Phase 2失敗: {e}") from e

    def _build_phase1_prompt(
        self,
        race_data: Dict[str, Any],
        ml_scores: List[Dict[str, Any]]
    ) -> str:
        """
        Phase 1プロンプト生成

        Args:
            race_data: レースデータ
            ml_scores: MLスコア

        Returns:
            プロンプト文字列
        """
        # レース情報セクション
        race_info = self._format_race_info(race_data)

        # ML上位馬セクション
        top_ml_horses = self._format_ml_top_horses(
            ml_scores[:PROMPT_ML_TOP_HORSES_PHASE1]
        )

        # 学習ポイントセクション
        learning_points_section = self._get_learning_points_section()

        # プロンプト組み立て
        prompt = f"""あなたは競馬予想の専門家です。機械学習の分析結果を元に、データ分析を行ってください。

{race_info}

## 機械学習による予想上位{PROMPT_ML_TOP_HORSES_PHASE1}頭

{top_ml_horses}

{learning_points_section}

## 分析タスク

機械学習の予想を踏まえ、以下の観点から分析してください：

1. **MLスコアの妥当性**: 上位予想馬の評価は妥当か？
2. **展開予想**: レースペースと各馬の脚質
3. **穴馬候補**: MLが見落としている可能性のある馬
4. **リスク要因**: 不安要素
5. **過去の学習ポイントとの関連**: 上記の学習ポイントが本レースに適用できるか

JSON形式で簡潔に出力してください。
"""

        return prompt

    def _build_phase2_prompt(
        self,
        race_data: Dict[str, Any],
        ml_scores: List[Dict[str, Any]],
        analysis: Dict[str, Any]
    ) -> str:
        """
        Phase 2プロンプト生成

        Args:
            race_data: レースデータ
            ml_scores: MLスコア
            analysis: Phase1分析結果

        Returns:
            プロンプト文字列
        """
        # ML上位馬セクション（Phase2用）
        top_ml_horses = self._format_ml_top_horses_phase2(
            ml_scores[:PROMPT_ML_TOP_HORSES_PHASE2]
        )

        # 学習ポイントセクション（詳細版）
        learning_points_section = self._get_learning_points_section_detailed()

        prompt = f"""Phase 1の分析を踏まえ、最終的な着順予想を行ってください。

## レース情報
- レース名: {race_data.get('race_name', '不明')}

## 機械学習による基準順位（上位{PROMPT_ML_TOP_HORSES_PHASE2}頭）
{top_ml_horses}

## Phase 1 分析結果
{json.dumps(analysis, ensure_ascii=False, indent=2)}

{learning_points_section}

## 予想タスク

機械学習の順位を**ベースライン**として、以下を考慮して調整してください：

1. Phase 1の分析結果（展開、穴馬、リスク要因）
2. 過去の学習ポイント（同様のケースでの失敗パターン）

**重要**: 過去の失敗から学び、同じミスを繰り返さないよう注意してください。

出力形式（JSON）:
{{
  "win_prediction": {{
    "first": {{"horse_number": 3, "horse_name": "...", "reason": "..."}},
    "second": {{"horse_number": 2, "horse_name": "...", "reason": "..."}},
    "third": {{"horse_number": 5, "horse_name": "...", "reason": "..."}}
  }},
  "betting_strategy": {{
    "recommended_tickets": [
      {{"ticket_type": "3連複", "numbers": [2, 3, 5], "amount": 500}}
    ],
    "total_investment": 500,
    "expected_return": 1000,
    "expected_roi": 2.0
  }}
}}
"""

        return prompt

    # ========================================
    # プロンプト生成ヘルパーメソッド
    # ========================================

    def _format_race_info(self, race_data: Dict[str, Any]) -> str:
        """レース情報セクションをフォーマット"""
        return f"""## レース情報
- レース名: {race_data.get('race_name', '不明')}
- 日付: {race_data.get('date', '不明')}
- 競馬場: {race_data.get('venue', '不明')}
- 距離: {race_data.get('distance', '不明')}m
- 馬場状態: {race_data.get('track_condition', '良')}"""

    def _format_ml_top_horses(self, top_horses: List[Dict[str, Any]]) -> str:
        """ML上位馬情報をフォーマット（Phase 1用）"""
        formatted = []
        for i, horse in enumerate(top_horses, 1):
            formatted.append(f"""### {i}位: {horse['horse_number']}番 {horse['horse_name']}
- 予想着順スコア: {horse['rank_score']:.2f}位
- 勝率予測: {horse['win_probability']:.1%}
- スピード指数: {horse['features'].get('speed_index_avg', 0):.1f}
- 上がり3F順位: {horse['features'].get('last3f_rank_avg', 0):.2f}位
- 騎手勝率: {horse['features'].get('jockey_win_rate', 0):.1%}
""")
        return "\n".join(formatted)

    def _format_ml_top_horses_phase2(self, top_horses: List[Dict[str, Any]]) -> str:
        """ML上位馬情報をフォーマット（Phase 2用）"""
        formatted = []
        for i, horse in enumerate(top_horses, 1):
            formatted.append(
                f"{i}位: {horse['horse_number']}番 {horse['horse_name']} "
                f"(勝率: {horse['win_probability']:.1%})"
            )
        return "\n".join(formatted)

    def _get_learning_points_section(self) -> str:
        """学習ポイントセクション取得（簡易版）"""
        try:
            learning_data = self.predictions_db.get_recent_learning_points(
                limit=PROMPT_LEARNING_POINTS_LIMIT,
                days_back=PROMPT_LEARNING_POINTS_DAYS_BACK
            )
            if not learning_data:
                return ""

            section = "\n## 過去の予想から学んだポイント\n\n"
            section += "直近の予想で学習した注意点を活かしてください：\n\n"

            for ld in learning_data:
                for point in ld['learning_points'][:PROMPT_LEARNING_POINTS_PER_RACE]:
                    section += f"- {point}\n"

            return section + "\n"
        except DatabaseError as e:
            logger.warning(f"学習ポイント取得失敗: {e}")
            return ""

    def _get_learning_points_section_detailed(self) -> str:
        """学習ポイントセクション取得（詳細版）"""
        try:
            learning_data = self.predictions_db.get_recent_learning_points(
                limit=PROMPT_LEARNING_POINTS_LIMIT,
                days_back=PROMPT_LEARNING_POINTS_DAYS_BACK
            )
            if not learning_data:
                return ""

            section = "\n## 過去の予想から学んだ教訓\n\n"

            for ld in learning_data:
                if ld['learning_points']:
                    section += f"**{ld['race_id']}** (外れ値率: {ld['outlier_rate']:.1%}):\n"
                    for point in ld['learning_points'][:3]:
                        section += f"- {point}\n"
                    section += "\n"

            return section
        except DatabaseError as e:
            logger.warning(f"学習ポイント取得失敗: {e}")
            return ""


# 使用例（テスト用）
if __name__ == "__main__":
    # ロギング設定
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # モックデータ
    mock_race_data = {
        'race_name': 'テストレース',
        'date': '2024-12-26',
        'venue': '東京',
        'distance': 2000,
        'track_condition': '良',
        'horses': [
            {'number': 1, 'name': 'テストホース1'},
            {'number': 2, 'name': 'テストホース2'},
            {'number': 3, 'name': 'テストホース3'},
        ]
    }

    # パイプライン実行
    try:
        pipeline = HybridPredictionPipeline()
        result = pipeline.predict(
            race_id='TEST001',
            race_data=mock_race_data,
            phase='all',
            save_to_db=False  # テストではDB保存しない
        )

        print("\n=== 予想結果 ===")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except PipelineError as e:
        logger.error(f"予想失敗: {e}")
