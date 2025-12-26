"""
ハイブリッド予想パイプライン

機械学習（XGBoost） + LLM（Gemini）による高精度予想システム
"""

import json
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime

from src.features.feature_pipeline import FeatureExtractor
from src.models.xgboost_model import HorseRacingXGBoost
from src.predict.llm import LLMClient


class HybridPredictionPipeline:
    """機械学習 + LLM ハイブリッド予想パイプライン"""

    def __init__(self, model_path: Optional[str] = None):
        """
        Args:
            model_path: 学習済みモデルのパス（省略時はモックモード）
        """
        self.feature_extractor = FeatureExtractor()
        self.ml_model = HorseRacingXGBoost()
        self.llm_client = LLMClient()

        # モデル読み込み（存在する場合）
        if model_path:
            self.ml_model.load(model_path)

    def predict(
        self,
        race_id: str,
        race_data: Dict,
        phase: str = "all",
        temperature: float = 0.3
    ) -> Dict:
        """
        ハイブリッド予想実行

        Args:
            race_id: レースID
            race_data: レースデータ（モック用）
            phase: 実行フェーズ（analyze/predict/all）
            temperature: LLM温度パラメータ

        Returns:
            dict: 予想結果
        """
        result = {
            'race_id': race_id,
            'timestamp': datetime.now().isoformat()
        }

        # Phase 0: 特徴量生成 & ML予測
        print("\n[Phase 0] 特徴量生成 & 機械学習予測")
        ml_scores = self._run_ml_prediction(race_id, race_data)
        result['ml_scores'] = ml_scores

        if phase == "analyze" or phase == "all":
            # Phase 1: LLMデータ分析（MLスコア付き）
            print("\n[Phase 1] データ分析（ML + LLM）")
            analysis = self._run_phase1(race_data, ml_scores, temperature)
            result['analysis'] = analysis

        if phase == "predict" or phase == "all":
            # Phase 2: LLM予想生成（ハイブリッド）
            print("\n[Phase 2] 予想生成（ハイブリッド）")
            prediction = self._run_phase2(
                race_data,
                ml_scores,
                result.get('analysis', {}),
                temperature
            )
            result['prediction'] = prediction

        return result

    def _run_ml_prediction(self, race_id: str, race_data: Dict) -> List[Dict]:
        """
        機械学習予測

        Args:
            race_id: レースID
            race_data: レースデータ

        Returns:
            list: MLスコア結果
        """
        num_horses = len(race_data.get('horses', []))

        # 特徴量抽出
        features_df = self.feature_extractor.extract_all_features(
            race_id,
            num_horses
        )

        # 予測
        rank_scores = self.ml_model.predict(features_df)
        win_probs = self.ml_model.predict_win_probability(features_df)

        # 結果をリストに変換
        results = []
        for i, horse in enumerate(race_data.get('horses', [])):
            results.append({
                'horse_number': horse.get('number', i + 1),
                'horse_name': horse.get('name', f'Horse {i + 1}'),
                'rank_score': float(rank_scores[i]),
                'win_probability': float(win_probs[i]),
                'features': features_df.iloc[i].to_dict()
            })

        # 着順スコアでソート
        results.sort(key=lambda x: x['rank_score'])

        # 順位を付与
        for rank, item in enumerate(results, 1):
            item['ml_predicted_rank'] = rank

        return results

    def _run_phase1(
        self,
        race_data: Dict,
        ml_scores: List[Dict],
        temperature: float
    ) -> Dict:
        """
        Phase 1: データ分析（ML + LLM）

        Args:
            race_data: レースデータ
            ml_scores: MLスコア
            temperature: LLM温度

        Returns:
            dict: 分析結果
        """
        # プロンプト生成
        prompt = self._build_phase1_prompt(race_data, ml_scores)

        # LLM実行
        response = self.llm_client.generate(
            prompt=prompt,
            temperature=temperature
        )

        try:
            # JSON解析を試みる
            return json.loads(response)
        except json.JSONDecodeError:
            # JSON解析失敗時はテキストとして返す
            return {'raw_response': response}

    def _run_phase2(
        self,
        race_data: Dict,
        ml_scores: List[Dict],
        analysis: Dict,
        temperature: float
    ) -> Dict:
        """
        Phase 2: 予想生成（ハイブリッド）

        Args:
            race_data: レースデータ
            ml_scores: MLスコア
            analysis: Phase1分析結果
            temperature: LLM温度

        Returns:
            dict: 予想結果
        """
        # プロンプト生成
        prompt = self._build_phase2_prompt(race_data, ml_scores, analysis)

        # LLM実行
        response = self.llm_client.generate(
            prompt=prompt,
            temperature=temperature
        )

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {'raw_response': response}

    def _build_phase1_prompt(self, race_data: Dict, ml_scores: List[Dict]) -> str:
        """Phase 1プロンプト生成"""

        # MLスコア上位3頭
        top3_ml = ml_scores[:3]

        prompt = f"""あなたは競馬予想の専門家です。機械学習の分析結果を元に、データ分析を行ってください。

## レース情報
- レース名: {race_data.get('race_name', '不明')}
- 日付: {race_data.get('date', '不明')}
- 競馬場: {race_data.get('venue', '不明')}
- 距離: {race_data.get('distance', '不明')}m
- 馬場状態: {race_data.get('track_condition', '良')}

## 機械学習による予想上位3頭

"""

        for i, horse in enumerate(top3_ml, 1):
            prompt += f"""### {i}位: {horse['horse_number']}番 {horse['horse_name']}
- 予想着順スコア: {horse['rank_score']:.2f}位
- 勝率予測: {horse['win_probability']:.1%}
- スピード指数: {horse['features'].get('speed_index_avg', 0):.1f}
- 上がり3F順位: {horse['features'].get('last3f_rank_avg', 0):.2f}位
- 騎手勝率: {horse['features'].get('jockey_win_rate', 0):.1%}

"""

        prompt += """
## 分析タスク

機械学習の予想を踏まえ、以下の観点から分析してください：

1. **MLスコアの妥当性**: 上位予想馬の評価は妥当か？
2. **展開予想**: レースペースと各馬の脚質
3. **穴馬候補**: MLが見落としている可能性のある馬
4. **リスク要因**: 不安要素

JSON形式で簡潔に出力してください。
"""

        return prompt

    def _build_phase2_prompt(
        self,
        race_data: Dict,
        ml_scores: List[Dict],
        analysis: Dict
    ) -> str:
        """Phase 2プロンプト生成"""

        # MLスコア上位5頭
        top5_ml = ml_scores[:5]

        prompt = f"""Phase 1の分析を踏まえ、最終的な着順予想を行ってください。

## レース情報
- レース名: {race_data.get('race_name', '不明')}

## 機械学習による基準順位（上位5頭）
"""

        for i, horse in enumerate(top5_ml, 1):
            prompt += f"{i}位: {horse['horse_number']}番 {horse['horse_name']} (勝率: {horse['win_probability']:.1%})\n"

        prompt += f"""
## Phase 1 分析結果
{json.dumps(analysis, ensure_ascii=False, indent=2)}

## 予想タスク

機械学習の順位を**ベースライン**として、展開を考慮して調整してください。

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


# 使用例（テスト用）
if __name__ == "__main__":
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
    pipeline = HybridPredictionPipeline()
    result = pipeline.predict(
        race_id='TEST001',
        race_data=mock_race_data,
        phase='all'
    )

    print("\n=== 予想結果 ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
