# 競馬予想システム 技術ドキュメント

## 概要

本システムは、JRA-VANの公式競馬データを活用し、機械学習（XGBoost）とLLM（Claude API）のハイブリッド予想を行います。

## システム構成

```
予想リクエスト
    ↓
┌─────────────────────────────────────────────┐
│           予想パイプライン                    │
├─────────────────────────────────────────────┤
│                                             │
│  ┌─────────────────┐   ┌─────────────────┐ │
│  │  機械学習（ML）   │   │   LLM予想       │ │
│  │  XGBoost        │   │   Claude API    │ │
│  └────────┬────────┘   └────────┬────────┘ │
│           │                      │          │
│           └──────────┬───────────┘          │
│                      ↓                      │
│           ┌─────────────────┐               │
│           │  ハイブリッド予想 │               │
│           │  最終結論       │               │
│           └─────────────────┘               │
└─────────────────────────────────────────────┘
    ↓
予想結果（着順・馬券推奨）
```

---

## 1. 機械学習（ML）側

### 1.1 モデル

- **アルゴリズム**: XGBoost（勾配ブースティング）
- **目的変数**: 着順スコア（1〜18）
- **パラメータ**:
  - `n_estimators`: 500（決定木の数）
  - `max_depth`: 6（木の深さ）
  - `learning_rate`: 0.05（学習率）
  - `subsample`: 0.8（サンプリング率）

### 1.2 特徴量（全92種類）

#### 基本情報
| 特徴量名 | 説明 | 型 |
|---------|------|-----|
| `age` | 馬齢 | int |
| `sex` | 性別（0:牡, 1:牝, 2:セン） | int |
| `kinryo` | 斤量（kg） | float |
| `wakuban` | 枠番（1-8） | int |
| `umaban` | 馬番（1-18） | int |

#### 馬体重
| 特徴量名 | 説明 | 型 |
|---------|------|-----|
| `horse_weight` | 馬体重（kg） | int |
| `weight_diff` | 前走比増減（kg） | int |

#### 脚質・位置取り
| 特徴量名 | 説明 | 型 |
|---------|------|-----|
| `running_style` | 脚質（1:逃げ,2:先行,3:差し,4:追込） | int |
| `position_avg_3f` | 3角平均位置（過去5走） | float |
| `position_avg_4f` | 4角平均位置（過去5走） | float |
| `corner_1_avg`〜`corner_4_avg` | 各コーナー平均位置 | float |

#### スピード指数
| 特徴量名 | 説明 | 型 |
|---------|------|-----|
| `speed_index_avg` | スピード指数（過去5走平均） | float |
| `speed_index_max` | スピード指数（過去5走最高） | float |
| `speed_index_recent` | 直近1走のスピード指数 | float |

#### 上がり3ハロン
| 特徴量名 | 説明 | 型 |
|---------|------|-----|
| `last3f_rank_avg` | 上がり3F順位平均 | float |
| `last3f_rank_best` | 上がり3F順位最良 | float |
| `last3f_time_avg` | 上がり3Fタイム平均（秒） | float |

#### 調教
| 特徴量名 | 説明 | 型 |
|---------|------|-----|
| `training_score` | 調教評価スコア（0-100） | float |
| `training_time` | 調教タイム（4F, 秒） | float |
| `training_rank` | 調教ランク（1:A, 2:B, 3:C） | int |
| `training_partner_result` | 併せ馬結果 | int |
| `training_intensity` | 追い切り強度 | int |

#### 血統
| 特徴量名 | 説明 | 型 |
|---------|------|-----|
| `sire_win_rate` | 父系産駒勝率 | float |
| `sire_distance_apt` | 父系距離適性 | float |
| `broodmare_sire_win_rate` | 母父産駒勝率 | float |
| `pedigree_class_score` | 血統クラススコア | float |

#### 騎手・調教師
| 特徴量名 | 説明 | 型 |
|---------|------|-----|
| `jockey_win_rate` | 騎手勝率 | float |
| `jockey_place_rate` | 騎手複勝率 | float |
| `jockey_change` | 乗り替わり（0:継続, 1:変更） | int |
| `trainer_win_rate` | 調教師勝率 | float |

#### オッズ・人気
| 特徴量名 | 説明 | 型 |
|---------|------|-----|
| `odds_win` | 単勝オッズ | float |
| `odds_place` | 複勝オッズ | float |
| `popularity` | 人気順位 | int |
| `odds_anomaly` | オッズ異常スコア | float |

### 1.3 予測値の見方

```python
# 着順スコア（rank_score）
# - 値が小さいほど上位予想
# - 1.0 = 1着予想、18.0 = 18着予想
# - 例: rank_score=2.3 → 2〜3着予想

# 勝率予測（win_probability）
# - 0.0〜1.0の範囲
# - 計算式: 1 / (1 + exp(rank_score - 1))
# - 例: 0.5 = 50%の勝率予測
```

### 1.4 現状と課題

**現状**:
- 特徴量抽出はモックデータを返している（実DB連携未実装）
- モデルは未訓練状態で動作

**今後の実装**:
1. 特徴量抽出をDBから取得するよう改修
2. 過去レースデータで学習を実行
3. 定期的な再学習パイプラインの構築

---

## 2. LLM側

### 2.1 使用モデル

- **プロバイダー**: Anthropic Claude API
- **モデル**: claude-3-5-sonnet-20241022
- **Temperature**: 0.5（予想生成時）

### 2.2 入力データ

LLMに渡されるデータ:

```
## レース情報
- レース名: 有馬記念
- 競馬場: 中山
- 距離: 2500m
- トラック: 芝
- グレード: G1

## 出走馬データ（各馬ごと）
### 1番 ○○○○
- 斤量: 58kg
- 騎手: 坂井瑠星
- 調教師: ○○厩舎
- 血統: 父ディープインパクト / 母父キングカメハメハ
- 過去5走:
  1. 2025/12/28 中山2500m 良 1着 2:32.5 (有馬記念)
  2. 2025/11/24 東京2400m 良 2着 2:25.5 (ジャパンカップ)
  ...
- 調教:
  20251225 坂路 4F52.3秒
  20251222 ウッド 4F51.8秒
- 単勝オッズ: 3.5
```

### 2.3 出力形式

```json
{
  "win_prediction": {
    "first": {
      "horse_number": 1,
      "horse_name": "馬名",
      "expected_odds": 3.5,
      "confidence": 0.8
    },
    "second": {...},
    "third": {...},
    "fourth": {...},  // 任意
    "fifth": {...},   // 任意
    "excluded": [     // 消し馬（任意）
      {
        "horse_number": 2,
        "horse_name": "馬名",
        "reason": "消す理由"
      }
    ]
  },
  "betting_strategy": {
    "recommended_tickets": [
      {
        "ticket_type": "3連複",
        "numbers": [1, 3, 5],
        "amount": 1000,
        "expected_payout": 5000
      }
    ]
  }
}
```

### 2.4 プロンプト設計

1. **分析プロンプト（analyze.txt）**
   - MLの予想を補正するための分析
   - 初物要素（初ブリンカー等）の検出
   - 展開予測とペース分析

2. **予想プロンプト（predict.txt）**
   - 回収率150%を目標とした馬券戦略
   - 期待値計算に基づく買い目選定
   - 穴馬・消し馬の根拠明示

---

## 3. 最終結論（ハイブリッド予想）

### 3.1 統合ロジック

```
1. ML予測（Phase 0）
   ↓ 着順スコア順に並び替え
2. LLM分析（Phase 1）
   ↓ ML予測の妥当性チェック、補正提案
3. LLM予想生成（Phase 2）
   ↓ ML + 分析結果を統合して最終予想
4. 馬券戦略立案
```

### 3.2 予想結果の見方

| 項目 | 説明 |
|------|------|
| `first` | 本命（◎）最も勝つ可能性が高い馬 |
| `second` | 対抗（○）本命に次ぐ評価 |
| `third` | 単穴（▲）3番手評価、穴っぽさあり |
| `fourth` | 連下（△）3着候補 |
| `fifth` | 注目（☆）大穴候補 |
| `excluded` | 消し（✕）馬券から外す馬 |

### 3.3 馬券推奨の見方

| 馬券種 | 説明 |
|--------|------|
| 単勝 | 1着を当てる。堅い馬の場合に推奨 |
| 複勝 | 3着以内を当てる。押さえとして |
| 馬連 | 1-2着の組み合わせ |
| ワイド | 3着以内の2頭の組み合わせ |
| 3連複 | 1-2-3着の組み合わせ（順不同） |
| 3連単 | 1-2-3着の順序も当てる |

### 3.4 期待値の見方

```
期待値 = 的中確率 × オッズ

- 期待値 > 1.0: 買い推奨
- 期待値 = 1.0: 損益分岐点
- 期待値 < 1.0: 買い非推奨

例: 的中確率20%、オッズ6.0倍の場合
    期待値 = 0.2 × 6.0 = 1.2 → 買い推奨
```

---

## 4. 学習・更新

### 4.1 学習データ

- ソース: JRA-VANの過去レースデータ
- 期間: 直近3年間
- 対象: 中央競馬全レース

### 4.2 学習コマンド（将来実装）

```bash
# 特徴量抽出
python -m src.features.extract_features --start-date 2022-01-01

# モデル学習
python -m src.models.train --data data/features.parquet --output models/xgboost_v1.pkl

# 予測実行
python -m src.predict.hybrid_pipeline --race-id 2025010106050811
```

### 4.3 反省・改善サイクル

```
レース終了後:
1. 実際の結果を取得
2. 予想との差分を分析
3. 学習ポイントをDBに保存
4. 次回予想時にプロンプトに反映
```

---

## 5. ファイル構成

```
src/
├── predict/
│   ├── pipeline.py           # 基本パイプライン
│   ├── hybrid_pipeline.py    # ML+LLMハイブリッド
│   ├── llm.py               # LLMクライアント（Gemini）
│   └── reflection_pipeline.py # 反省パイプライン
├── features/
│   └── feature_pipeline.py   # 特徴量抽出
├── models/
│   ├── xgboost_model.py     # XGBoostモデル
│   ├── train.py             # 学習スクリプト
│   └── incremental_learning.py # 増分学習
├── services/
│   ├── claude_client.py     # Claude API
│   └── prediction_service.py # 予想サービス
└── api/
    └── routes/predictions.py # 予想APIエンドポイント

prompts/
├── analyze.txt              # 分析プロンプト
├── predict.txt              # 予想プロンプト
└── reflect.txt              # 反省プロンプト
```

---

## 6. API

### 予想生成

```
POST /api/predictions/generate
```

リクエスト:
```json
{
  "race_id": "2025010106050811",
  "is_final": false,
  "total_investment": 10000
}
```

レスポンス:
```json
{
  "prediction_id": "uuid",
  "race_id": "2025010106050811",
  "race_name": "有馬記念",
  "prediction_result": {
    "win_prediction": {...},
    "betting_strategy": {...}
  },
  "total_investment": 10000,
  "expected_return": 15000,
  "expected_roi": 1.5
}
```

---

## 7. 今後の改善計画

1. **特徴量抽出の実DB対応**
   - モックデータから実データへ移行
   - 過去成績、調教データの正確な取得

2. **モデル学習パイプライン**
   - 初期学習の実行
   - 定期再学習の自動化

3. **予想精度の向上**
   - 特徴量の追加・選択
   - ハイパーパラメータチューニング

4. **反省サイクルの自動化**
   - レース結果取得の自動化
   - 学習ポイントの自動抽出
