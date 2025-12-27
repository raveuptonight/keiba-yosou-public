"""
結果照合 & 失敗分析パイプライン

予想と実際の結果を比較し、ML・LLM両方の学習を実行

Phase 3A: ML外れ値分析 & 自動再学習
Phase 3B: LLM失敗分析 & 学習ポイント抽出
"""

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from src.predict.llm import LLMClient
from src.models.xgboost_model import HorseRacingXGBoost
from src.models.incremental_learning import IncrementalLearner
from src.db.predictions_db import PredictionsDB
from src.config import (
    ML_MIN_RETRAIN_SAMPLES,
    LLM_REFLECTION_TEMPERATURE,
)
from src.exceptions import (
    PipelineError,
    AnalysisError,
    LLMError,
    ModelTrainError,
    DatabaseError,
    DataParseError,
)

# ロガー設定
logger = logging.getLogger(__name__)


class ReflectionPipeline:
    """
    結果照合 & 失敗分析パイプライン

    予想結果と実際のレース結果を照合し、以下の処理を実行：
    1. ML外れ値分析・自動再学習
    2. LLM失敗分析・学習ポイント抽出
    3. 学習履歴のDB保存

    Attributes:
        llm_client: LLMクライアント
        ml_model: XGBoostモデル
        incremental_learner: 継続的学習マネージャー
        predictions_db: 予想結果DBクライアント
    """

    def __init__(self, ml_model: HorseRacingXGBoost):
        """
        Args:
            ml_model: 学習対象のXGBoostモデル

        Raises:
            PipelineError: パイプライン初期化に失敗した場合
        """
        try:
            self.llm_client = LLMClient()
            self.ml_model = ml_model
            self.incremental_learner = IncrementalLearner(ml_model)
            self.predictions_db = PredictionsDB()
            logger.info("ReflectionPipeline初期化完了")
        except Exception as e:
            logger.error(f"ReflectionPipeline初期化失敗: {e}")
            raise PipelineError(f"ReflectionPipeline初期化失敗: {e}") from e

    def analyze_result(
        self,
        prediction_data: Dict[str, Any],
        actual_result: Dict[str, Any],
        prediction_id: Optional[int] = None,
        auto_retrain: bool = True,
        save_to_db: bool = True
    ) -> Dict[str, Any]:
        """
        予想と結果を照合し、ML・LLM両方の失敗分析を実行

        Args:
            prediction_data: 予想時のデータ（race_id, ml_scores, analysis, prediction含む）
            actual_result: 実際のレース結果（rankings含む）
            prediction_id: 予想ID（DBに保存済みの場合）
            auto_retrain: 自動再学習フラグ
            save_to_db: DBに保存するか

        Returns:
            統合分析結果（以下のキーを含む）:
                - timestamp: 分析時刻
                - race_id: レースID
                - ml_analysis: ML外れ値分析結果
                - ml_retrain: ML再学習結果（auto_retrain=Trueの場合）
                - llm_analysis: LLM失敗分析結果
                - learning_points: 抽出された学習ポイント
                - summary: 統合サマリー
                - learning_id: DB保存ID（save_to_db=Trueの場合）

        Raises:
            AnalysisError: 分析に失敗した場合
            ModelTrainError: モデル再学習に失敗した場合
        """
        logger.info("=" * 60)
        logger.info("Phase 3: 結果照合 & 失敗分析")
        logger.info("=" * 60)
        print("\n" + "=" * 60)
        print("Phase 3: 結果照合 & 失敗分析")
        print("=" * 60)

        result: Dict[str, Any] = {
            'timestamp': datetime.now().isoformat(),
            'race_id': prediction_data.get('race_id')
        }

        try:
            # Phase 3A: ML外れ値分析 & 再学習
            logger.info("[Phase 3A] ML外れ値分析 & 再学習")
            print("\n[Phase 3A] 機械学習モデルの外れ値分析")

            ml_analysis = self._analyze_ml_outliers(prediction_data, actual_result)
            result['ml_analysis'] = ml_analysis

            # 学習データに追加
            self._add_to_training_data(prediction_data, actual_result)

            # 自動再学習
            retrain_result: Optional[Dict[str, Any]] = None
            if auto_retrain:
                try:
                    retrain_result = self.incremental_learner.retrain_model(
                        min_samples=ML_MIN_RETRAIN_SAMPLES
                    )
                    result['ml_retrain'] = retrain_result
                    logger.info(f"ML再学習: {retrain_result['status']}")
                except ModelTrainError as e:
                    logger.error(f"ML再学習失敗: {e}")
                    result['ml_retrain'] = {'status': 'failed', 'error': str(e)}

            # Phase 3B: LLM失敗分析
            logger.info("[Phase 3B] LLM失敗分析")
            print("\n[Phase 3B] LLM失敗分析")

            llm_analysis = self._analyze_llm_prediction(
                prediction_data,
                actual_result,
                ml_analysis
            )
            result['llm_analysis'] = llm_analysis

            # 学習ポイント抽出
            learning_points = self._extract_learning_points(llm_analysis)
            result['learning_points'] = learning_points
            logger.info(f"学習ポイント抽出: {len(learning_points)}件")

            # 統合レポート
            result['summary'] = self._create_summary(ml_analysis, llm_analysis)

            # データベースに保存
            if save_to_db:
                try:
                    learning_id = self.predictions_db.save_learning_history(
                        prediction_id=prediction_id,
                        race_id=prediction_data.get('race_id'),
                        actual_result=actual_result,
                        ml_analysis=ml_analysis,
                        llm_analysis=llm_analysis,
                        learning_points=learning_points,
                        ml_retrain_result=retrain_result,
                        accuracy_metrics=result['summary']
                    )
                    result['learning_id'] = learning_id
                    logger.info(f"学習履歴保存成功: learning_id={learning_id}")
                    print(f"\n✅ 学習履歴保存: learning_id={learning_id}")
                except DatabaseError as e:
                    logger.error(f"学習履歴保存失敗: {e}")
                    print(f"\n⚠️  学習履歴保存失敗: {e}")
                    # DB保存失敗は致命的でないため、処理続行

            logger.info("Phase 3完了")
            return result

        except (AnalysisError, ModelTrainError) as e:
            # 既知のエラーは再スロー
            logger.error(f"結果照合パイプライン失敗: {e}")
            raise
        except Exception as e:
            # 予期しないエラー
            logger.exception(f"結果照合パイプライン予期しないエラー: {e}")
            raise PipelineError(f"結果照合パイプライン失敗: {e}") from e

    def _analyze_ml_outliers(
        self,
        prediction_data: Dict[str, Any],
        actual_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        ML外れ値分析

        Args:
            prediction_data: 予想データ
            actual_result: 実際の結果

        Returns:
            ML分析結果（outlier_rate, avg_error, outliers等含む）

        Raises:
            AnalysisError: 分析に失敗した場合
        """
        try:
            # 外れ値分析
            outlier_analysis = self.incremental_learner.analyze_outliers(
                prediction_data,
                actual_result
            )

            # 結果表示
            logger.info(
                f"外れ値率: {outlier_analysis['outlier_rate']:.1%}, "
                f"平均誤差: {outlier_analysis['avg_error']:.2f}着"
            )
            print(f"  外れ値率: {outlier_analysis['outlier_rate']:.1%}")
            print(f"  平均誤差: {outlier_analysis['avg_error']:.2f}着")
            print(f"  外れ値数: {outlier_analysis['outlier_count']}頭")

            if outlier_analysis['outliers']:
                print("\n  外れ値:")
                for outlier in outlier_analysis['outliers'][:3]:  # 上位3頭のみ表示
                    print(f"    {outlier['horse_number']}番 {outlier['horse_name']}")
                    print(
                        f"      予測: {outlier['predicted_rank']:.1f}着 → "
                        f"実際: {outlier['actual_rank']}着"
                    )
                    print(f"      誤差: {outlier['error']:.1f}着 ({outlier['outlier_type']})")

            # 改善提案
            suggestions = self.incremental_learner.suggest_improvements(outlier_analysis)
            outlier_analysis['improvement_suggestions'] = suggestions

            if suggestions:
                print("\n  改善提案:")
                for s in suggestions:
                    print(f"    [{s['priority']}] {s['suggestion']}")

            return outlier_analysis

        except Exception as e:
            logger.error(f"ML外れ値分析失敗: {e}")
            raise AnalysisError(f"ML外れ値分析失敗: {e}") from e

    def _add_to_training_data(
        self,
        prediction_data: Dict[str, Any],
        actual_result: Dict[str, Any]
    ) -> None:
        """
        学習データに追加

        Args:
            prediction_data: 予想データ
            actual_result: 実際の結果

        Raises:
            AnalysisError: データ追加に失敗した場合
        """
        try:
            import pandas as pd

            ml_scores = prediction_data['ml_scores']
            rankings = actual_result.get('rankings', {})

            # 特徴量とラベルを抽出
            features_list: List[Dict[str, Any]] = []
            ranks_list: List[int] = []

            for horse_data in ml_scores:
                horse_number = horse_data['horse_number']
                actual_rank = rankings.get(horse_number)

                if actual_rank is not None:
                    features_list.append(horse_data['features'])
                    ranks_list.append(actual_rank)

            if features_list:
                features_df = pd.DataFrame(features_list)
                ranks_series = pd.Series(ranks_list)

                self.incremental_learner.add_training_sample(features_df, ranks_series)
                logger.debug(f"学習データ追加: {len(features_list)}サンプル")
            else:
                logger.warning("追加可能な学習データがありません")

        except Exception as e:
            logger.error(f"学習データ追加失敗: {e}")
            raise AnalysisError(f"学習データ追加失敗: {e}") from e

    def _analyze_llm_prediction(
        self,
        prediction_data: Dict[str, Any],
        actual_result: Dict[str, Any],
        ml_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        LLM失敗分析

        Args:
            prediction_data: 予想データ
            actual_result: 実際の結果
            ml_analysis: ML分析結果

        Returns:
            LLM分析結果

        Raises:
            AnalysisError: LLM分析に失敗した場合
        """
        try:
            # プロンプト生成
            prompt = self._build_llm_reflection_prompt(
                prediction_data,
                actual_result,
                ml_analysis
            )

            # LLM実行
            logger.debug("LLM反省分析開始")
            response = self.llm_client.generate(
                prompt=prompt,
                temperature=LLM_REFLECTION_TEMPERATURE
            )

            # JSON解析
            try:
                analysis = json.loads(response)
                logger.debug("LLM分析JSON解析成功")
                return analysis
            except json.JSONDecodeError as e:
                logger.warning(f"JSON解析失敗、raw_responseとして返却: {e}")
                return {'raw_response': response}

        except LLMError as e:
            logger.error(f"LLM分析失敗: {e}")
            raise AnalysisError(f"LLM分析失敗: {e}") from e
        except Exception as e:
            logger.error(f"LLM分析予期しないエラー: {e}")
            raise AnalysisError(f"LLM分析失敗: {e}") from e

    def _build_llm_reflection_prompt(
        self,
        prediction_data: Dict[str, Any],
        actual_result: Dict[str, Any],
        ml_analysis: Dict[str, Any]
    ) -> str:
        """
        LLM反省プロンプト生成

        Args:
            prediction_data: 予想データ
            actual_result: 実際の結果
            ml_analysis: ML分析結果

        Returns:
            プロンプト文字列
        """
        # 実際の結果を整形
        rankings = actual_result.get('rankings', {})
        sorted_results = sorted(rankings.items(), key=lambda x: x[1])[:3]

        actual_1st = sorted_results[0] if len(sorted_results) > 0 else (None, None)
        actual_2nd = sorted_results[1] if len(sorted_results) > 1 else (None, None)
        actual_3rd = sorted_results[2] if len(sorted_results) > 2 else (None, None)

        prompt = f"""あなたは競馬予想の分析専門家です。予想と実際の結果を比較し、失敗要因を分析してください。

## 実際の結果

- **1着**: {actual_1st[0]}番 (予測着順: {self._get_predicted_rank(prediction_data, actual_1st[0]):.1f}着)
- **2着**: {actual_2nd[0]}番 (予測着順: {self._get_predicted_rank(prediction_data, actual_2nd[0]):.1f}着)
- **3着**: {actual_3rd[0]}番 (予測着順: {self._get_predicted_rank(prediction_data, actual_3rd[0]):.1f}着)

## 機械学習の外れ値分析

- 外れ値率: {ml_analysis['outlier_rate']:.1%}
- 平均誤差: {ml_analysis['avg_error']:.2f}着
- 外れ値数: {ml_analysis['outlier_count']}頭

### 主な外れ値
"""

        for outlier in ml_analysis.get('outliers', [])[:3]:
            prompt += (
                f"- {outlier['horse_number']}番: "
                f"予測{outlier['predicted_rank']:.1f}着 → "
                f"実際{outlier['actual_rank']}着 ({outlier['outlier_type']})\n"
            )

        prompt += f"""
## あなたの予想内容

### Phase 1 分析
{json.dumps(prediction_data.get('analysis', {}), ensure_ascii=False, indent=2)}

### Phase 2 予想
{json.dumps(prediction_data.get('prediction', {}), ensure_ascii=False, indent=2)}

---

## 分析タスク

1. **MLの外れ値について**: なぜこれらの馬が大きく外れたか？
2. **展開予想の的中度**: 予想した展開は当たっていたか？
3. **見落とした要因**: 予想時に考慮できなかった要因は？
4. **学習ポイント**: 次回同様のケースで注意すべき点は？

JSON形式で簡潔に出力してください。
"""

        return prompt

    def _get_predicted_rank(
        self,
        prediction_data: Dict[str, Any],
        horse_number: Optional[int]
    ) -> float:
        """
        予測着順を取得

        Args:
            prediction_data: 予想データ
            horse_number: 馬番号

        Returns:
            予測着順スコア
        """
        if horse_number is None:
            return 0.0

        for horse_data in prediction_data.get('ml_scores', []):
            if horse_data['horse_number'] == horse_number:
                return horse_data['rank_score']

        return 0.0

    def _extract_learning_points(self, llm_analysis: Dict[str, Any]) -> List[str]:
        """
        LLM分析から学習ポイントを抽出

        Args:
            llm_analysis: LLM分析結果

        Returns:
            学習ポイントリスト
        """
        learning_points: List[str] = []

        try:
            # LLM分析から学習ポイントを取得
            if 'learning_points' in llm_analysis:
                lp = llm_analysis['learning_points']
                if isinstance(lp, list):
                    learning_points.extend(lp)
                elif isinstance(lp, str):
                    learning_points.append(lp)

            # 他のキーからも学習ポイントを抽出
            if '見落とした要因' in llm_analysis:
                factors = llm_analysis['見落とした要因']
                if isinstance(factors, list):
                    learning_points.extend([f"見落とした要因: {f}" for f in factors])
                elif isinstance(factors, str):
                    learning_points.append(f"見落とした要因: {factors}")

            if '次回注意点' in llm_analysis:
                notes = llm_analysis['次回注意点']
                if isinstance(notes, list):
                    learning_points.extend([f"注意: {n}" for n in notes])
                elif isinstance(notes, str):
                    learning_points.append(f"注意: {notes}")

            # 重複削除
            learning_points = list(set(learning_points))

            logger.debug(f"学習ポイント抽出完了: {len(learning_points)}件")

        except Exception as e:
            logger.warning(f"学習ポイント抽出で警告: {e}")

        return learning_points

    def _create_summary(
        self,
        ml_analysis: Dict[str, Any],
        llm_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        統合サマリー作成

        Args:
            ml_analysis: ML分析結果
            llm_analysis: LLM分析結果

        Returns:
            統合サマリー
        """
        return {
            'ml_accuracy': 1.0 - ml_analysis['outlier_rate'],
            'avg_error': ml_analysis['avg_error'],
            'outlier_count': ml_analysis['outlier_count'],
            'llm_insights': llm_analysis.get('learning_points', [])[:3],
            'action_items': ml_analysis.get('improvement_suggestions', [])
        }


# 使用例
if __name__ == "__main__":
    # ロギング設定
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    from src.models.xgboost_model import HorseRacingXGBoost

    # モデル読み込み
    model = HorseRacingXGBoost()

    # パイプライン
    pipeline = ReflectionPipeline(model)

    # モックデータ
    prediction_data = {
        'race_id': 'TEST001',
        'ml_scores': [
            {
                'horse_number': 1,
                'horse_name': 'Horse1',
                'rank_score': 2.5,
                'features': {'speed_index_avg': 85}
            }
        ],
        'analysis': {},
        'prediction': {}
    }

    actual_result = {
        'rankings': {1: 8}
    }

    # 分析実行
    try:
        result = pipeline.analyze_result(
            prediction_data,
            actual_result,
            save_to_db=False  # テストではDB保存しない
        )
        print("\n=== 分析結果 ===")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (AnalysisError, PipelineError) as e:
        logger.error(f"分析失敗: {e}")
