# 機械学習 + LLM ハイブリッド予想システム

XGBoost（機械学習）とGemini（LLM）を組み合わせた高精度予想システムの設計・実装ガイド。

---

## システム設計

### 全体フロー

```
┌─────────────────────────────────────────────────────────┐
│ Phase 0: データ準備 & 特徴量生成（機械学習）               │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  JRA-VANデータ                                           │
│    ↓                                                    │
│  特徴量エンジニアリング                                    │
│    - スピード指数                                         │
│    - 上がり3F順位                                         │
│    - 騎手・調教師成績                                      │
│    - コース適性                                           │
│    ↓                                                    │
│  XGBoostモデル                                           │
│    - 各馬の着順予測スコア（1-18の範囲）                     │
│    - 勝率予測（0-1の範囲）                                 │
│                                                         │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Phase 1: データ分析（LLM）                                │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  入力:                                                   │
│    - レース基本情報                                       │
│    - 各馬の過去走データ                                    │
│    - MLスコア（着順予測、勝率予測）← 機械学習の結果         │
│                                                         │
│  LLMタスク:                                              │
│    - データの傾向分析                                      │
│    - 展開予想                                             │
│    - 穴馬候補発見                                         │
│                                                         │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Phase 2: 予想生成（LLM + MLスコア統合）                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  入力:                                                   │
│    - Phase 1の分析結果                                    │
│    - MLスコア                                            │
│                                                         │
│  統合ロジック:                                            │
│    - MLスコアを基準順位として使用                          │
│    - LLMが展開・文脈を考慮して調整                         │
│    - 最終的な着順予想                                      │
│                                                         │
│  出力:                                                   │
│    - 本命・対抗・穴馬                                      │
│    - 推奨馬券                                             │
│    - 期待値・ROI                                          │
│                                                         │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Phase 3: 反省・改善（結果分析）                            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  - MLスコアの精度検証                                      │
│  - LLM予想との比較                                        │
│  - 特徴量の寄与度分析                                      │
│  - 次回への改善提案                                        │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 特徴量エンジニアリング

### 実装する特徴量

```python
# src/features/feature_pipeline.py

class FeatureExtractor:
    """JRA-VANデータから特徴量を抽出"""

    def extract_features(self, race_id, horse_id):
        """
        各馬の特徴量を抽出

        Returns:
            dict: 特徴量辞書
        """
        features = {}

        # 1. 基本情報
        features['age'] = self._get_horse_age(horse_id)
        features['weight'] = self._get_weight(race_id, horse_id)
        features['sex'] = self._get_sex(horse_id)

        # 2. スピード指数（過去5走平均）
        features['speed_index_avg'] = self._calculate_speed_index(horse_id, n=5)
        features['speed_index_max'] = self._calculate_speed_index_max(horse_id, n=5)

        # 3. 上がり3F順位（過去5走平均）
        features['last3f_rank_avg'] = self._get_last3f_rank(horse_id, n=5)

        # 4. 騎手成績
        jockey_id = self._get_jockey(race_id, horse_id)
        features['jockey_win_rate'] = self._get_jockey_stats(jockey_id, 'win_rate')
        features['jockey_place_rate'] = self._get_jockey_stats(jockey_id, 'place_rate')

        # 5. 調教師成績
        trainer_id = self._get_trainer(horse_id)
        features['trainer_win_rate'] = self._get_trainer_stats(trainer_id, 'win_rate')

        # 6. コース適性
        course_code = self._get_course_code(race_id)
        features['course_fit_score'] = self._get_course_fit(horse_id, course_code)

        # 7. 距離適性
        distance = self._get_distance(race_id)
        features['distance_fit_score'] = self._get_distance_fit(horse_id, distance)

        # 8. 馬場適性
        track_condition = self._get_track_condition(race_id)
        features['track_condition_score'] = self._get_track_condition_fit(horse_id, track_condition)

        # 9. 休養明け
        features['days_since_last_race'] = self._get_days_since_last_race(horse_id)

        # 10. クラス
        features['class_rank'] = self._get_class_rank(race_id)

        return features
```

### スピード指数の計算

```python
def _calculate_speed_index(self, horse_id, n=5):
    """
    スピード指数を計算

    スピード指数 = (基準タイム - 走破タイム) × 距離係数 + 馬場補正
    """
    past_races = self._get_past_races(horse_id, n)

    speed_indices = []
    for race in past_races:
        # 基準タイム（そのコース・距離の平均タイム）
        base_time = self._get_base_time(race['course'], race['distance'])

        # 走破タイム
        finish_time = race['finish_time']

        # 距離係数（200mあたり1.0）
        distance_factor = race['distance'] / 200

        # 馬場補正
        track_adjustment = self._get_track_adjustment(race['track_condition'])

        # スピード指数計算
        speed_index = (base_time - finish_time) * distance_factor + track_adjustment
        speed_indices.append(speed_index)

    return np.mean(speed_indices) if speed_indices else 0
```

---

## 機械学習モデル（XGBoost）

### モデル訓練

```python
# src/models/xgboost_model.py

import xgboost as xgb
from sklearn.model_selection import train_test_split
import pickle

class HorseRacingXGBoost:
    """競馬予想XGBoostモデル"""

    def __init__(self):
        self.model = None
        self.feature_names = None

    def train(self, X, y):
        """
        モデル訓練

        Args:
            X: 特徴量（DataFrame）
            y: 目的変数（着順）
        """
        # データ分割
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        # XGBoostモデル
        self.model = xgb.XGBRegressor(
            objective='reg:squarederror',  # 回帰タスク
            n_estimators=1000,
            learning_rate=0.05,
            max_depth=6,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            early_stopping_rounds=50
        )

        # 訓練
        self.model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=100
        )

        # 特徴量名を保存
        self.feature_names = X.columns.tolist()

        print(f"訓練完了 - Test RMSE: {self._evaluate(X_test, y_test)}")

    def predict(self, X):
        """
        着順予測

        Returns:
            array: 予測着順（1-18の範囲）
        """
        if self.model is None:
            raise ValueError("モデルが訓練されていません")

        predictions = self.model.predict(X)
        # 1-18の範囲にクリップ
        return np.clip(predictions, 1, 18)

    def predict_win_probability(self, X):
        """
        勝率予測

        Returns:
            array: 勝率（0-1の範囲）
        """
        predictions = self.predict(X)
        # 着順予測を勝率に変換（1着予測 = 高勝率）
        # シグモイド関数で変換
        return 1 / (1 + np.exp(predictions - 1))

    def get_feature_importance(self):
        """特徴量重要度を取得"""
        importance = self.model.feature_importances_
        return dict(zip(self.feature_names, importance))

    def save(self, filepath):
        """モデル保存"""
        with open(filepath, 'wb') as f:
            pickle.dump({
                'model': self.model,
                'feature_names': self.feature_names
            }, f)

    def load(self, filepath):
        """モデル読み込み"""
        with open(filepath, 'rb') as f:
            data = pickle.load(f)
            self.model = data['model']
            self.feature_names = data['feature_names']
```

---

## LLMプロンプト統合

### Phase 1: データ分析（MLスコア付き）

```python
# prompts/analyze_with_ml.txt

あなたは競馬予想の専門家です。以下のレースデータと機械学習の分析結果を元に、徹底的にデータ分析を行ってください。

## レース情報
{race_info}

## 各馬のデータ（機械学習スコア付き）

### 1番 {horse_1_name}
**基本情報:**
- 馬齢: {age}
- 騎手: {jockey_name}（勝率: {jockey_win_rate}%）
- 調教師: {trainer_name}（勝率: {trainer_win_rate}%）

**過去走データ:**
{past_races}

**機械学習分析結果:**
- 予想着順スコア: {ml_rank_score:.2f} 位（1に近いほど上位予想）
- 勝率予測: {ml_win_prob:.1%}
- スピード指数: {speed_index:.1f}
- 上がり3F順位平均: {last3f_rank:.2f}位
- コース適性スコア: {course_fit:.2f}（1.0が最適）

**特徴量詳細:**
- 距離適性: {distance_fit:.2f}
- 馬場適性: {track_condition_fit:.2f}
- 休養日数: {days_since_last_race}日

---

### 2番 {horse_2_name}
...（同様に全馬分）

---

## 分析タスク

機械学習モデルは客観的な数値分析を行いましたが、以下の観点から人間的な洞察を加えてください：

1. **機械学習スコアの妥当性確認**
   - MLが高評価した馬の根拠は妥当か？
   - 過大評価・過小評価されている馬はいないか？

2. **展開予想**
   - 逃げ馬、先行馬、差し馬のバランス
   - ペース予想（速い/遅い）
   - 展開的に有利な馬

3. **穴馬候補の発見**
   - MLスコアは低いが、展開次第で好走しそうな馬
   - オッズと実力の乖離が大きい馬

4. **リスク要因**
   - MLが見落としている可能性のあるリスク
   - 不安要素（休養明け、コース初、昇級など）

5. **総合判断**
   - 本命候補（ML + 展開的に有利）
   - 対抗候補
   - 穴馬候補

JSON形式で出力してください。
```

### Phase 2: 予想生成（ハイブリッド）

```python
# prompts/predict_hybrid.txt

Phase 1の分析結果と機械学習スコアを統合して、最終的な着順予想を行ってください。

## Phase 1 分析結果
{phase1_result}

## 機械学習による基準順位
1位: {ml_rank_1}番 {horse_name_1}（勝率予測: {win_prob_1:.1%}）
2位: {ml_rank_2}番 {horse_name_2}（勝率予測: {win_prob_2:.1%}）
3位: {ml_rank_3}番 {horse_name_3}（勝率予測: {win_prob_3:.1%}）
...

## 予想タスク

機械学習の順位を**ベースライン**として、以下を考慮して調整してください：

1. **展開による調整**
   - MLが予想した順位で展開的に不利な馬 → 順位を下げる
   - MLが予想した順位より展開的に有利な馬 → 順位を上げる

2. **オッズとの兼ね合い**
   - 人気薄でも期待値が高い馬を重視

3. **最終予想**
   - 本命（◎）: ML上位 + 展開有利
   - 対抗（○）: ML中位 + 展開次第で上位
   - 単穴（▲）: ML下位 だが展開次第で激走

4. **推奨馬券**
   - 期待値200%以上を目指す
   - MLスコアと展開を考慮した買い目

JSON形式で出力してください。
```

---

## 実装例

```python
# src/pipeline.py（改修版）

from src.features.feature_pipeline import FeatureExtractor
from src.models.xgboost_model import HorseRacingXGBoost
from src.predict.llm import LLMClient

class HybridPredictionPipeline:
    """機械学習 + LLM ハイブリッド予想パイプライン"""

    def __init__(self):
        self.feature_extractor = FeatureExtractor()
        self.ml_model = HorseRacingXGBoost()
        self.llm_client = LLMClient()

        # 学習済みモデルをロード
        self.ml_model.load('models/xgboost_v1.pkl')

    def predict(self, race_id):
        """
        ハイブリッド予想実行

        Args:
            race_id: レースID

        Returns:
            dict: 予想結果
        """
        # Phase 0: 特徴量生成 & ML予測
        print("[Phase 0] 特徴量生成 & 機械学習予測")
        ml_scores = self._run_ml_prediction(race_id)

        # Phase 1: LLMデータ分析（MLスコア付き）
        print("[Phase 1] データ分析（ML + LLM）")
        analysis = self._run_phase1(race_id, ml_scores)

        # Phase 2: LLM予想生成（ハイブリッド）
        print("[Phase 2] 予想生成（ハイブリッド）")
        prediction = self._run_phase2(race_id, ml_scores, analysis)

        return {
            'ml_scores': ml_scores,
            'analysis': analysis,
            'prediction': prediction
        }

    def _run_ml_prediction(self, race_id):
        """機械学習予測"""
        horses = self._get_race_horses(race_id)

        results = []
        for horse in horses:
            # 特徴量抽出
            features = self.feature_extractor.extract_features(race_id, horse['id'])

            # DataFrameに変換
            X = pd.DataFrame([features])

            # 予測
            rank_score = self.ml_model.predict(X)[0]
            win_prob = self.ml_model.predict_win_probability(X)[0]

            results.append({
                'horse_number': horse['number'],
                'horse_name': horse['name'],
                'rank_score': rank_score,
                'win_probability': win_prob,
                'features': features
            })

        # 着順スコアでソート
        results.sort(key=lambda x: x['rank_score'])

        return results

    def _run_phase1(self, race_id, ml_scores):
        """Phase 1: データ分析"""
        # プロンプト生成（MLスコアを含める）
        prompt = self._build_phase1_prompt(race_id, ml_scores)

        # LLM実行
        response = self.llm_client.generate(
            prompt=prompt,
            temperature=0.3
        )

        return response

    def _run_phase2(self, race_id, ml_scores, analysis):
        """Phase 2: 予想生成"""
        # プロンプト生成
        prompt = self._build_phase2_prompt(race_id, ml_scores, analysis)

        # LLM実行
        response = self.llm_client.generate(
            prompt=prompt,
            temperature=0.3
        )

        return response
```

---

## 期待される効果

### 機械学習の強み
- ✅ 客観的な数値分析
- ✅ 大量データの処理
- ✅ パターン認識
- ✅ 過去の傾向を学習

### LLMの強み
- ✅ 文脈理解
- ✅ 展開予想
- ✅ 複雑な要因の統合
- ✅ 人間的な洞察

### ハイブリッドの利点
- **🎯 高精度**: 両方の長所を活かす
- **📊 説明可能性**: MLスコア + LLMの理由付け
- **🔧 柔軟性**: MLスコアを基準に、LLMが調整
- **🎲 期待値最大化**: 客観的スコア + オッズ戦略

---

## 次のステップ

1. **特徴量実装** (1週間)
   - `src/features/` 配下の実装
   - JRA-VANデータからの抽出

2. **モデル訓練** (3日)
   - 過去データで学習
   - 検証・チューニング

3. **プロンプト改修** (2日)
   - MLスコア統合
   - Phase 1, 2の改修

4. **テスト** (継続)
   - 実レースで検証
   - 精度測定

実装を始めますか？
