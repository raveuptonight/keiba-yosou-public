"""
競馬予想パイプライン

3つのフェーズを統合して実行するメインモジュール：
1. データ分析（Analyze）
2. 予想生成（Predict）
3. 反省・改善（Reflect）
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from src.predict.llm import LLMClient, get_llm_client


class HorsePredictionPipeline:
    """競馬予想パイプライン - 回収率200%を目指す"""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        db_connection=None,
        prompts_dir: str = "prompts",
    ):
        """
        Args:
            llm_client: LLMクライアント（Noneの場合は環境変数から自動生成）
            db_connection: データベース接続（現時点ではオプション）
            prompts_dir: プロンプトファイルのディレクトリ
        """
        self.llm = llm_client or get_llm_client(
            os.getenv("LLM_PROVIDER", "gemini")
        )
        self.db = db_connection
        self.prompts_dir = Path(prompts_dir)

        # プロンプトテンプレートを読み込み
        self.analyze_prompt = self._load_prompt("analyze.txt")
        self.predict_prompt = self._load_prompt("predict.txt")
        self.reflect_prompt = self._load_prompt("reflect.txt")

    def _load_prompt(self, filename: str) -> str:
        """プロンプトテンプレートを読み込み"""
        prompt_path = self.prompts_dir / filename
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        return prompt_path.read_text(encoding="utf-8")

    def analyze(
        self, race_data: Dict[str, Any], temperature: float = 0.3
    ) -> Dict[str, Any]:
        """
        フェーズ1: データ分析

        Args:
            race_data: レースデータ（race_info, horses, past_performance等）
            temperature: LLMの生成パラメータ

        Returns:
            Dict[str, Any]: 分析結果（JSON形式）
        """
        # プロンプトにデータを埋め込み
        prompt = self.analyze_prompt.format(
            race_info=json.dumps(race_data.get("race_info", {}), ensure_ascii=False, indent=2),
            horse_data=json.dumps(race_data.get("horses", []), ensure_ascii=False, indent=2),
            past_performance=json.dumps(
                race_data.get("past_performance", {}), ensure_ascii=False, indent=2
            ),
        )

        # LLMで分析実行
        print("=" * 60)
        print("フェーズ1: データ分析を開始...")
        print("=" * 60)

        response = self.llm.generate(prompt, temperature=temperature, max_tokens=4000)

        # JSON抽出（```json ブロック内を抽出）
        analysis_result = self._extract_json(response)

        print("✓ 分析完了")
        return analysis_result

    def predict(
        self,
        race_data: Dict[str, Any],
        analysis_result: Dict[str, Any],
        temperature: float = 0.5,
    ) -> Dict[str, Any]:
        """
        フェーズ2: 予想生成

        Args:
            race_data: レースデータ
            analysis_result: フェーズ1の分析結果
            temperature: LLMの生成パラメータ

        Returns:
            Dict[str, Any]: 予想結果（JSON形式）
        """
        # プロンプトにデータを埋め込み
        prompt = self.predict_prompt.format(
            race_info=json.dumps(race_data.get("race_info", {}), ensure_ascii=False, indent=2),
            analysis_result=json.dumps(analysis_result, ensure_ascii=False, indent=2),
            odds_data=json.dumps(
                self._extract_odds(race_data), ensure_ascii=False, indent=2
            ),
        )

        # LLMで予想実行
        print("=" * 60)
        print("フェーズ2: 予想生成を開始...")
        print("=" * 60)

        response = self.llm.generate(prompt, temperature=temperature, max_tokens=4000)

        # JSON抽出
        prediction_result = self._extract_json(response)

        print("✓ 予想完了")
        print(
            f"推奨投資額: {prediction_result.get('total_investment', 0)}円"
        )
        print(
            f"期待回収額: {prediction_result.get('expected_total_return', 0)}円"
        )
        print(f"期待ROI: {prediction_result.get('expected_roi', 0):.2%}")

        return prediction_result

    def reflect(
        self,
        race_data: Dict[str, Any],
        analysis_result: Dict[str, Any],
        prediction: Dict[str, Any],
        actual_result: Dict[str, Any],
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """
        フェーズ3: 反省・改善

        Args:
            race_data: レースデータ
            analysis_result: フェーズ1の分析結果
            prediction: フェーズ2の予想結果
            actual_result: 実際のレース結果
            temperature: LLMの生成パラメータ

        Returns:
            Dict[str, Any]: 反省・改善結果（JSON形式）
        """
        # 馬券の収支を計算
        betting_result = self._calculate_betting_result(
            prediction, actual_result
        )

        # プロンプトにデータを埋め込み
        prompt = self.reflect_prompt.format(
            race_info=json.dumps(race_data.get("race_info", {}), ensure_ascii=False, indent=2),
            analysis_result=json.dumps(analysis_result, ensure_ascii=False, indent=2),
            prediction=json.dumps(prediction, ensure_ascii=False, indent=2),
            actual_result=json.dumps(actual_result, ensure_ascii=False, indent=2),
            betting_result=json.dumps(betting_result, ensure_ascii=False, indent=2),
        )

        # LLMで反省実行
        print("=" * 60)
        print("フェーズ3: 反省・改善を開始...")
        print("=" * 60)

        response = self.llm.generate(prompt, temperature=temperature, max_tokens=4000)

        # JSON抽出
        reflection_result = self._extract_json(response)

        print("✓ 反省完了")
        print(f"総合評価: {reflection_result.get('overall_evaluation', {}).get('summary', 'N/A')}")

        return reflection_result

    def run_full_pipeline(
        self, race_data: Dict[str, Any], actual_result: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        3フェーズを統合実行

        Args:
            race_data: レースデータ
            actual_result: 実際のレース結果（結果判明後に実行する場合）

        Returns:
            Dict[str, Any]: 全フェーズの結果
        """
        # フェーズ1: 分析
        analysis_result = self.analyze(race_data)

        # フェーズ2: 予想
        prediction = self.predict(race_data, analysis_result)

        # フェーズ3: 反省（結果がある場合のみ）
        reflection = None
        if actual_result is not None:
            reflection = self.reflect(
                race_data, analysis_result, prediction, actual_result
            )

        return {
            "analysis": analysis_result,
            "prediction": prediction,
            "reflection": reflection,
            "timestamp": datetime.now().isoformat(),
        }

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """LLMの応答からJSON部分を抽出"""
        # ```json ... ``` ブロックを探す
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            json_text = text[start:end].strip()
        elif "```" in text:
            # ```だけの場合も対応
            start = text.find("```") + 3
            end = text.find("```", start)
            json_text = text[start:end].strip()
        else:
            # JSONブロックがない場合はそのままパース試行
            json_text = text.strip()

        try:
            return json.loads(json_text)
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")
            print(f"Text: {json_text[:500]}...")
            # エラー時は空のdictを返す
            return {}

    def _extract_odds(self, race_data: Dict[str, Any]) -> Dict[str, Any]:
        """レースデータからオッズ情報を抽出"""
        odds_data = {}
        for horse in race_data.get("horses", []):
            horse_num = horse.get("horse_number")
            if horse_num:
                odds_data[horse_num] = horse.get("odds", {})
        return odds_data

    def _calculate_betting_result(
        self, prediction: Dict[str, Any], actual_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """馬券の収支を計算"""
        total_investment = prediction.get("total_investment", 0)
        total_return = 0

        # 実際の配当データ
        payouts = actual_result.get("final_results", {}).get("payouts", {})

        # 各馬券の的中判定と払戻計算
        # （簡易実装、実際にはもっと詳細な計算が必要）

        return {
            "total_investment": total_investment,
            "total_return": total_return,
            "roi": total_return / total_investment if total_investment > 0 else 0,
            "profit": total_return - total_investment,
        }


if __name__ == "__main__":
    # モックデータでテスト実行
    import json

    # モックデータ読み込み
    with open("tests/mock_data/sample_race.json", "r", encoding="utf-8") as f:
        race_data = json.load(f)

    # パイプライン実行
    pipeline = HorsePredictionPipeline()

    try:
        # 分析のみ実行（予想まで実行するとAPI消費するので注意）
        print("モックデータでパイプラインテスト...")
        result = pipeline.analyze(race_data)
        print("\n分析結果:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
