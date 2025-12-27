# フィードバックループ設計

予想→結果→分析→学習の継続的改善サイクル

---

## システムフロー

```
┌─────────────────────────────────────────────────────────┐
│ Phase 1-2: 予想実行                                      │
│  - MLスコア + LLM分析                                    │
│  - 着順予想、推奨馬券                                     │
└──────────────────┬──────────────────────────────────────┘
                   │ 予想結果を保存（predictions.predictions）
                   ▼
┌─────────────────────────────────────────────────────────┐
│ レース実施 → 結果確定                                     │
└──────────────────┬──────────────────────────────────────┘
                   │ 実際の結果
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Phase 3A: 機械学習モデルの外れ値分析 & 再学習              │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ 1. 外れ値の特定                                          │
│    ✓ 予測着順 vs 実際着順の誤差計算                      │
│    ✓ 誤差3着以上を「外れ値」として抽出                    │
│                                                         │
│ 2. 外れ値の分類                                          │
│    ✓ 過大評価: 上位予想が大外れ                          │
│    ✓ 過小評価: 穴馬を見逃し                              │
│                                                         │
│ 3. 特徴量分析                                            │
│    ✓ 外れ値の共通特徴を抽出                              │
│    ✓ どの特徴量が誤判断の原因か？                        │
│                                                         │
│ 4. 学習データ蓄積                                        │
│    ✓ 今回の特徴量 + 実際の着順を蓄積                     │
│    ✓ 一定サンプル数（100件）で自動再学習                 │
│                                                         │
│ 5. モデル再学習                                          │
│    ✓ 蓄積データで XGBoost 再訓練                         │
│    ✓ 特徴量重要度の更新                                  │
│    ✓ 新モデル保存 & バージョン管理                       │
│                                                         │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Phase 3B: LLM失敗分析                                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ 1. 予想と結果の比較                                      │
│    ✓ 的中項目: 本命、対抗、穴馬                          │
│    ✓ 外れ項目: どの馬が予想外の着順に？                   │
│                                                         │
│ 2. 失敗要因の分析                                        │
│    ✓ LLM分析の妥当性: 展開予想は当たったか？             │
│    ✓ 見落とした要因: 馬場、展開、アクシデントなど         │
│                                                         │
│ 3. 学習ポイントの抽出                                    │
│    ✓ 次回同様のケースで注意すべき点                       │
│    ✓ プロンプト改善案                                    │
│                                                         │
└──────────────────┬──────────────────────────────────────┘
                   │ 学習内容を保存（predictions.results）
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Phase 4: 次回予想への反映                                 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ ML側:                                                    │
│   - 再学習済みモデルで予測                                │
│   - 更新された特徴量重要度                                │
│                                                         │
│ LLM側:                                                   │
│   - 過去の失敗パターンをプロンプトに含める                │
│   - 「過去、同様のレースで外した要因」                     │
│   - 「注意すべきポイント」                                │
│                                                         │
└─────────────────────────────────────────────────────────┘
                   │
                   └─→ 次回予想に活用 → Phase 1-2
```

---

## データベース設計（追加）

### predictions.results テーブル（拡張）

```sql
CREATE TABLE predictions.results (
    id SERIAL PRIMARY KEY,
    prediction_id INTEGER NOT NULL,

    -- 実際の結果
    actual_result JSONB NOT NULL,  -- 実際のレース結果
    actual_1st INTEGER,            -- 実際の1着馬番
    actual_2nd INTEGER,            -- 実際の2着馬番
    actual_3rd INTEGER,            -- 実際の3着馬番

    -- 予想との比較
    predicted_1st INTEGER,         -- 予想した1着
    predicted_2nd INTEGER,         -- 予想した2着
    predicted_3rd INTEGER,         -- 予想した3着

    hit_1st BOOLEAN,               -- 1着的中
    hit_2nd BOOLEAN,               -- 2着的中
    hit_3rd BOOLEAN,               -- 3着的中

    -- 収支
    total_return INTEGER,
    profit INTEGER,
    actual_roi NUMERIC(5,2),

    -- 精度分析
    prediction_accuracy NUMERIC(3,2),  -- 全体的中精度
    ml_accuracy NUMERIC(3,2),          -- MLスコア精度
    llm_accuracy NUMERIC(3,2),         -- LLM予想精度

    -- 失敗分析（Phase 3の結果）
    failure_analysis JSONB,        -- 失敗要因の詳細分析
    learning_points JSONB,         -- 学習ポイント
    improvement_suggestions JSONB, -- 改善提案

    -- メタデータ
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_prediction FOREIGN KEY (prediction_id)
        REFERENCES predictions.predictions(id) ON DELETE CASCADE
);
```

### predictions.learning_history テーブル（新規）

```sql
CREATE TABLE predictions.learning_history (
    id SERIAL PRIMARY KEY,
    result_id INTEGER NOT NULL,

    -- 学習内容
    learning_type VARCHAR(50),     -- 'feature_weight', 'prompt_improvement', 'pattern'
    learning_category VARCHAR(50), -- 'pace', 'track_condition', 'jockey', etc.
    learning_content JSONB,        -- 学習内容の詳細

    -- 適用条件
    applicable_conditions JSONB,   -- どういう条件で適用するか

    -- 有効性
    applied_count INTEGER DEFAULT 0,     -- 適用回数
    success_count INTEGER DEFAULT 0,     -- 成功回数
    effectiveness NUMERIC(3,2),          -- 有効性スコア

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_result FOREIGN KEY (result_id)
        REFERENCES predictions.results(id) ON DELETE CASCADE
);
```

---

## Phase 3: 結果照合 & 失敗分析

### プロンプト設計

```python
# prompts/reflect_and_learn.txt

あなたは競馬予想の分析専門家です。予想と実際の結果を比較し、失敗要因を徹底的に分析してください。

## 予想内容

### Phase 1 分析結果
{phase1_analysis}

### Phase 2 予想結果
{phase2_prediction}

### 機械学習スコア
{ml_scores}

---

## 実際の結果

- **1着**: {actual_1st}番 {actual_1st_name}
- **2着**: {actual_2nd}番 {actual_2nd_name}
- **3着**: {actual_3rd}番 {actual_3rd_name}

---

## 予想との比較

### 的中状況
- 本命（◎）: {predicted_1st}番 → 実際: {actual_rank_of_predicted_1st}着 {hit_or_miss_1st}
- 対抗（○）: {predicted_2nd}番 → 実際: {actual_rank_of_predicted_2nd}着 {hit_or_miss_2nd}
- 単穴（▲）: {predicted_3rd}番 → 実際: {actual_rank_of_predicted_3rd}着 {hit_or_miss_3rd}

### 馬券結果
- 投資額: {total_investment}円
- 回収額: {total_return}円
- 収支: {profit}円
- ROI: {actual_roi}%

---

## 分析タスク

以下の観点から、**なぜ予想が外れたのか**を詳細に分析してください：

### 1. 機械学習スコアの精度検証

各馬のML予測着順と実際の着順を比較：

| 馬番 | 馬名 | ML予測着順 | 実際の着順 | 差分 | 評価 |
|------|------|-----------|-----------|------|------|
| 1番  | ... | 5.2位     | 3着       | -2.2 | 過小評価 |
| 2番  | ... | 2.1位     | 10着      | +7.9 | 過大評価 |
| ...  | ... | ...       | ...       | ...  | ... |

**分析ポイント:**
- MLが大きく外した馬（差分±3以上）はどれか？
- その馬の特徴量で何が原因と考えられるか？
- 特徴量の重み調整が必要か？

### 2. LLM分析・予想の妥当性検証

**Phase 1の展開予想:**
- 予想したペース: {predicted_pace}
- 実際のペース: {actual_pace}
- 展開予想の的中度: {pace_accuracy}

**Phase 2の着順予想理由:**
- 本命の選定理由: {reason_for_1st}
- 実際の結果との乖離: {gap_for_1st}

**分析ポイント:**
- 展開予想は当たっていたか？
- 展開予想が当たっていたのに着順が外れた理由は？
- 展開予想が外れた原因は何か？

### 3. 見落とした要因の特定

以下の観点から、予想時に考慮できなかった要因を分析：

- **馬場状態の変化**: レース中の馬場悪化・改善
- **展開の誤算**: 逃げ馬の失速、差し馬の不発など
- **アクシデント**: 出遅れ、進路妨害、騎手ミスなど
- **隠れた好材料**: 見落としていた好走要因
- **過大評価要因**: 人気馬の凡走理由

### 4. 学習ポイントの抽出

今回の失敗から、次回同様のケースで注意すべき点を抽出：

**例:**
- 「雨後の芝で、スピード指数だけで判断するのは危険」
- 「逃げ馬が複数いる場合、ペース崩壊を想定すべき」
- 「昇級初戦の馬は、過去成績を過信しない」

### 5. 改善提案

次回予想の精度向上のための具体的な改善案：

- **特徴量の追加・調整**: 「馬場適性の重み増加」
- **プロンプト改善**: 「展開予想をより詳細に」
- **MLモデル改善**: 「クラス昇級の補正追加」

---

## 出力形式（JSON）

以下のJSON形式で出力してください：

```json
{
  "hit_summary": {
    "hit_1st": true/false,
    "hit_2nd": true/false,
    "hit_3rd": true/false,
    "overall_accuracy": 0.33
  },
  "ml_analysis": {
    "overestimated_horses": [
      {"horse_number": 2, "predicted": 2.1, "actual": 10, "gap": 7.9, "reason": "..."}
    ],
    "underestimated_horses": [
      {"horse_number": 1, "predicted": 5.2, "actual": 3, "gap": -2.2, "reason": "..."}
    ],
    "ml_accuracy": 0.65
  },
  "llm_analysis": {
    "pace_prediction_accuracy": 0.8,
    "prediction_reasoning_validity": "...",
    "llm_accuracy": 0.7
  },
  "overlooked_factors": [
    {"factor": "馬場悪化", "impact": "high", "description": "..."},
    {"factor": "ペース崩壊", "impact": "medium", "description": "..."}
  ],
  "learning_points": [
    {
      "category": "track_condition",
      "point": "雨後の芝は、スピード指数より上がり3F重視",
      "applicable_conditions": {"track_condition": "稍重", "surface": "芝"}
    },
    {
      "category": "pace",
      "point": "逃げ馬3頭以上の場合、ペース過多を想定",
      "applicable_conditions": {"leading_horses": ">=3"}
    }
  ],
  "improvement_suggestions": [
    {"type": "feature", "suggestion": "馬場適性スコアの重み+20%"},
    {"type": "prompt", "suggestion": "展開予想にペース崩壊リスク評価を追加"},
    {"type": "model", "suggestion": "昇級補正の強化"}
  ]
}
```
```

---

## 実装例

```python
# src/reflection_pipeline.py

from typing import Dict
import json
from datetime import datetime

from src.predict.llm import LLMClient
from src.db.results import ResultsDB


class ReflectionPipeline:
    """結果照合 & 失敗分析パイプライン"""

    def __init__(self):
        self.llm_client = LLMClient()
        self.results_db = ResultsDB()

    def analyze_result(
        self,
        prediction_id: int,
        actual_result: Dict
    ) -> Dict:
        """
        予想と結果を照合し、失敗分析を実行

        Args:
            prediction_id: 予想ID
            actual_result: 実際のレース結果

        Returns:
            dict: 分析結果
        """
        # 1. 予想データ取得
        prediction = self.results_db.get_prediction(prediction_id)

        # 2. 的中状況の確認
        hit_summary = self._check_hits(prediction, actual_result)

        # 3. LLMで失敗分析
        analysis = self._run_failure_analysis(
            prediction,
            actual_result,
            hit_summary
        )

        # 4. 結果を保存
        self.results_db.save_result(
            prediction_id=prediction_id,
            actual_result=actual_result,
            analysis=analysis
        )

        # 5. 学習ポイントを保存
        self._save_learning_points(
            prediction_id,
            analysis['learning_points']
        )

        return analysis

    def _check_hits(self, prediction: Dict, actual_result: Dict) -> Dict:
        """的中状況を確認"""
        predicted_1st = prediction['prediction_result']['win_prediction']['first']['horse_number']
        predicted_2nd = prediction['prediction_result']['win_prediction']['second']['horse_number']
        predicted_3rd = prediction['prediction_result']['win_prediction']['third']['horse_number']

        actual_1st = actual_result['1st']
        actual_2nd = actual_result['2nd']
        actual_3rd = actual_result['3rd']

        return {
            'hit_1st': predicted_1st == actual_1st,
            'hit_2nd': predicted_2nd == actual_2nd,
            'hit_3rd': predicted_3rd == actual_3rd,
            'overall_accuracy': sum([
                predicted_1st == actual_1st,
                predicted_2nd == actual_2nd,
                predicted_3rd == actual_3rd
            ]) / 3.0
        }

    def _run_failure_analysis(
        self,
        prediction: Dict,
        actual_result: Dict,
        hit_summary: Dict
    ) -> Dict:
        """LLMで失敗分析を実行"""
        prompt = self._build_reflection_prompt(
            prediction,
            actual_result,
            hit_summary
        )

        response = self.llm_client.generate(
            prompt=prompt,
            temperature=0.2  # 分析は低温度で
        )

        return json.loads(response)

    def _save_learning_points(self, prediction_id: int, learning_points: list):
        """学習ポイントをDBに保存"""
        for point in learning_points:
            self.results_db.save_learning_point(
                prediction_id=prediction_id,
                category=point['category'],
                content=point['point'],
                conditions=point['applicable_conditions']
            )

    def get_relevant_learning_points(self, race_conditions: Dict) -> list:
        """
        次回予想時に、関連する過去の学習ポイントを取得

        Args:
            race_conditions: レース条件（馬場、距離、コースなど）

        Returns:
            list: 関連する学習ポイント
        """
        return self.results_db.query_learning_points(race_conditions)
```

---

## Phase 1-2への学習内容の反映

```python
# prompts/analyze_with_learning.txt (Phase 1改良版)

あなたは競馬予想の専門家です。機械学習の分析結果と**過去の失敗から学んだ教訓**を元に、データ分析を行ってください。

## レース情報
{race_info}

## 機械学習スコア
{ml_scores}

## ⚠️ 過去の学習ポイント（同様の条件で失敗した教訓）

{learning_points}

**注意事項:**
上記の学習ポイントを踏まえ、同じ過ちを繰り返さないようにしてください。

---

## 分析タスク
...
```

---

## 期待される効果

### 継続的改善サイクル（ダブルループ学習）

```
           ML側の学習ループ              LLM側の学習ループ
                ↓                            ↓
予想 → 結果 → 外れ値分析 → モデル再学習    失敗分析 → 学習ポイント抽出
  ↑         ↓                             ↓
  |     新モデル                     プロンプト改善
  |         ↓                             ↓
  └─────── 次回予想に反映 ←─────────────────┘
```

### 精度向上の仕組み

#### ML側の継続学習
1. **外れ値検出**: 予測誤差3着以上を特定
2. **特徴量分析**: 外れ値の共通パターンを発見
3. **データ蓄積**: 実際の結果を学習データに追加
4. **自動再学習**: 100サンプル毎にモデル更新
5. **特徴量重要度更新**: 新しい重みで次回予測

#### LLM側の継続学習
1. **失敗パターン分析**: なぜ展開予想が外れたか
2. **学習ポイントDB化**: 条件別に教訓を保存
3. **プロンプト改善**: 過去の失敗を警告として含める

### 目標
- **的中率向上**: 継続的な学習で精度アップ
- **回収率200%達成**: 失敗分析→改善サイクル
- **説明可能性**: なぜ外れたかが明確

---

次のステップ: 実装しますか？
