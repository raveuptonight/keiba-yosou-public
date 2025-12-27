"""
結果照合 & 失敗分析パイプライン

予想と実際の結果を比較し、ML・LLM両方の学習を実行
"""

import json
from typing import Dict, List, Optional
from datetime import datetime

from src.predict.llm import LLMClient
from src.models.xgboost_model import HorseRacingXGBoost
from src.models.incremental_learning import IncrementalLearner
from src.db.predictions_db import PredictionsDB


class ReflectionPipeline:
    """結果照合 & 失敗分析パイプライン"""

    def __init__(self, ml_model: HorseRacingXGBoost):
        """
        Args:
            ml_model: 学習対象のXGBoostモデル
        """
        self.llm_client = LLMClient()
        self.ml_model = ml_model
        self.incremental_learner = IncrementalLearner(ml_model)
        self.predictions_db = PredictionsDB()

    def analyze_result(
        self,
        prediction_data: Dict,
        actual_result: Dict,
        prediction_id: Optional[int] = None,
        auto_retrain: bool = True,
        save_to_db: bool = True
    ) -> Dict:
        """
        予想と結果を照合し、ML・LLM両方の失敗分析を実行

        Args:
            prediction_data: 予想時のデータ
            actual_result: 実際のレース結果
            prediction_id: 予想ID（DBに保存済みの場合）
            auto_retrain: 自動再学習フラグ
            save_to_db: DBに保存するか

        Returns:
            dict: 統合分析結果
        """
        print("\n" + "=" * 60)
        print("Phase 3: 結果照合 & 失敗分析")
        print("=" * 60)

        result = {
            'timestamp': datetime.now().isoformat(),
            'race_id': prediction_data.get('race_id')
        }

        # Phase 3A: ML外れ値分析 & 再学習
        print("\n[Phase 3A] 機械学習モデルの外れ値分析")
        ml_analysis = self._analyze_ml_outliers(prediction_data, actual_result)
        result['ml_analysis'] = ml_analysis

        # 学習データに追加
        self._add_to_training_data(prediction_data, actual_result)

        # 自動再学習
        retrain_result = None
        if auto_retrain:
            retrain_result = self.incremental_learner.retrain_model(min_samples=100)
            result['ml_retrain'] = retrain_result

        # Phase 3B: LLM失敗分析
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
                print(f"\n✅ 学習履歴保存: learning_id={learning_id}")
            except Exception as e:
                print(f"\n⚠️  学習履歴保存失敗: {e}")

        return result

    def _analyze_ml_outliers(
        self,
        prediction_data: Dict,
        actual_result: Dict
    ) -> Dict:
        """
        ML外れ値分析

        Args:
            prediction_data: 予想データ
            actual_result: 実際の結果

        Returns:
            dict: ML分析結果
        """
        # 外れ値分析
        outlier_analysis = self.incremental_learner.analyze_outliers(
            prediction_data,
            actual_result
        )

        print(f"  外れ値率: {outlier_analysis['outlier_rate']:.1%}")
        print(f"  平均誤差: {outlier_analysis['avg_error']:.2f}着")
        print(f"  外れ値数: {outlier_analysis['outlier_count']}頭")

        if outlier_analysis['outliers']:
            print("\n  外れ値:")
            for outlier in outlier_analysis['outliers'][:3]:  # 上位3頭のみ表示
                print(f"    {outlier['horse_number']}番 {outlier['horse_name']}")
                print(f"      予測: {outlier['predicted_rank']:.1f}着 → 実際: {outlier['actual_rank']}着")
                print(f"      誤差: {outlier['error']:.1f}着 ({outlier['outlier_type']})")

        # 改善提案
        suggestions = self.incremental_learner.suggest_improvements(outlier_analysis)
        outlier_analysis['improvement_suggestions'] = suggestions

        if suggestions:
            print("\n  改善提案:")
            for s in suggestions:
                print(f"    [{s['priority']}] {s['suggestion']}")

        return outlier_analysis

    def _add_to_training_data(
        self,
        prediction_data: Dict,
        actual_result: Dict
    ):
        """学習データに追加"""
        import pandas as pd

        ml_scores = prediction_data['ml_scores']
        rankings = actual_result.get('rankings', {})

        # 特徴量とラベルを抽出
        features_list = []
        ranks_list = []

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

    def _analyze_llm_prediction(
        self,
        prediction_data: Dict,
        actual_result: Dict,
        ml_analysis: Dict
    ) -> Dict:
        """
        LLM失敗分析

        Args:
            prediction_data: 予想データ
            actual_result: 実際の結果
            ml_analysis: ML分析結果

        Returns:
            dict: LLM分析結果
        """
        # プロンプト生成
        prompt = self._build_llm_reflection_prompt(
            prediction_data,
            actual_result,
            ml_analysis
        )

        # LLM実行
        response = self.llm_client.generate(
            prompt=prompt,
            temperature=0.2
        )

        try:
            analysis = json.loads(response)
        except json.JSONDecodeError:
            analysis = {'raw_response': response}

        return analysis

    def _build_llm_reflection_prompt(
        self,
        prediction_data: Dict,
        actual_result: Dict,
        ml_analysis: Dict
    ) -> str:
        """LLM反省プロンプト生成"""

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
            prompt += f"- {outlier['horse_number']}番: 予測{outlier['predicted_rank']:.1f}着 → 実際{outlier['actual_rank']}着 ({outlier['outlier_type']})\n"

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

    def _get_predicted_rank(self, prediction_data: Dict, horse_number: int) -> float:
        """予測着順を取得"""
        for horse_data in prediction_data.get('ml_scores', []):
            if horse_data['horse_number'] == horse_number:
                return horse_data['rank_score']
        return 0.0

    def _extract_learning_points(self, llm_analysis: Dict) -> List[str]:
        """
        LLM分析から学習ポイントを抽出

        Args:
            llm_analysis: LLM分析結果

        Returns:
            list: 学習ポイントリスト
        """
        learning_points = []

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

        return learning_points

    def _create_summary(self, ml_analysis: Dict, llm_analysis: Dict) -> Dict:
        """統合サマリー作成"""
        return {
            'ml_accuracy': 1.0 - ml_analysis['outlier_rate'],
            'avg_error': ml_analysis['avg_error'],
            'outlier_count': ml_analysis['outlier_count'],
            'llm_insights': llm_analysis.get('learning_points', [])[:3],
            'action_items': ml_analysis.get('improvement_suggestions', [])
        }


# 使用例
if __name__ == "__main__":
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
    result = pipeline.analyze_result(prediction_data, actual_result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
