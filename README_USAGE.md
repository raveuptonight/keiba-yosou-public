# 競馬予想システム - 使い方ガイド

**目標: 回収率200%達成！**

## クイックスタート

### 1. 環境設定

```bash
# 仮想環境を有効化
source venv/bin/activate

# .envファイルにAPIキーを設定
# GEMINI_API_KEY=あなたのAPIキー
```

### 2. モックデータでテスト実行

```bash
# フェーズ1のみ（分析）
python scripts/run_prediction.py --mock --phase analyze

# フェーズ1+2（分析→予想）
python scripts/run_prediction.py --mock --phase predict

# 全フェーズ（分析→予想→反省）
python scripts/run_prediction.py --mock --phase all
```

### 3. 結果の確認

実行結果は `results/` ディレクトリに保存されます。

```bash
# 最新の結果を確認
ls -lt results/
cat results/prediction_20241226_120000.json
```

## システム構成

### 3つのフェーズ

```
フェーズ1: データ分析（Analyze）
    ↓
    過去データから傾向を分析
    馬の強み・弱みを特定
    穴馬候補を発見

フェーズ2: 予想生成（Predict）
    ↓
    具体的な着順予想
    馬券購入戦略の立案
    期待値の計算

フェーズ3: 反省・改善（Reflect）
    ↓
    予想と結果の比較
    失敗要因の分析
    次回への改善策
```

### ファイル構成

```
keiba-yosou/
├── prompts/              # LLMプロンプトテンプレート
│   ├── analyze.txt       # データ分析用
│   ├── predict.txt       # 予想生成用
│   └── reflect.txt       # 反省・改善用
│
├── src/
│   ├── db/
│   │   └── connection.py # DB接続管理
│   ├── predict/
│   │   └── llm.py        # LLMクライアント
│   └── pipeline.py       # メインパイプライン
│
├── scripts/
│   └── run_prediction.py # 実行スクリプト
│
├── tests/
│   └── mock_data/        # テスト用データ
│       ├── sample_race.json
│       └── sample_result.json
│
└── results/              # 予想結果の保存先
```

## 使い方の詳細

### モックデータでの練習

```bash
# 分析のみ（API使用量少）
python scripts/run_prediction.py --mock --phase analyze

# temperatureを変更（創造性を調整）
python scripts/run_prediction.py --mock --phase predict --temperature 0.7

# 結果の保存先を指定
python scripts/run_prediction.py --mock --phase all --output-dir my_results
```

### 実データでの予想（DB構築後）

```bash
# レースIDを指定して実行
python scripts/run_prediction.py --race-id 202412280506 --phase all
```

## プロンプトのカスタマイズ

`prompts/` ディレクトリのファイルを編集することで、LLMへの指示を変更できます。

### 例: 分析の重点を変更

`prompts/analyze.txt` を編集:

```
## 分析タスク

以下の観点から徹底的に分析してください：

### 1. 血統分析を最重視 ← ここを強調
- 父馬の特徴
...
```

## トラブルシューティング

### LLMのJSON出力エラー

温度パラメータを下げる:
```bash
python scripts/run_prediction.py --mock --temperature 0.1
```

### API制限エラー

フェーズごとに分けて実行:
```bash
# まず分析だけ
python scripts/run_prediction.py --mock --phase analyze

# 少し待ってから予想
python scripts/run_prediction.py --mock --phase predict
```

## 次のステップ

1. **モックデータで動作確認** ✓ 今ここ
2. **DB接続とデータ取得の実装** ← 次はこれ
3. **特徴量エンジニアリング**
4. **予想精度の検証**
5. **本番運用**

## 回収率200%達成のために

- 人気薄の好走馬を見つける
- オッズと実力の乖離を狙う
- 過剰人気馬を避ける
- 期待値計算を徹底する
- 反省フェーズで継続改善

頑張りましょう！
