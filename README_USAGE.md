# 競馬予想システム - 使い方ガイド

**目標: 回収率200%達成！**

## クイックスタート

### 1. 環境設定

```bash
# Docker Composeで起動
docker-compose up -d

# または仮想環境を使用
source venv/bin/activate
pip install -r requirements.txt
```

### 2. モデル学習

```bash
# 機械学習モデルの学習
python -m src.models.advanced_train

# 高速学習版
python -m src.models.fast_train
```

### 3. 予想の実行

```bash
# Discord Bot経由（推奨）
# !predict 2025122809050812

# またはAPI経由
curl http://localhost:8000/api/predictions/race/2025122809050812
```

## システム構成

### 機械学習モデル

```
XGBoost + LightGBM アンサンブル
    ↓
特徴量:
- 馬の基本情報（馬齢、性別、斤量）
- 過去成績（勝率、連対率、3着内率）
- 血統情報（父馬・母父の産駒成績）
- 騎手・調教師の成績
- コース適性

出力:
- 勝率（%）
- 順位予測
- 順位分布（モンテカルロシミュレーション）
- 信頼度
```

### ファイル構成

```
keiba-yosou/
├── src/
│   ├── models/           # 機械学習モデル
│   │   ├── advanced_train.py   # 学習スクリプト
│   │   ├── prediction_output.py # 予測出力フォーマット
│   │   └── fast_train.py       # 高速学習版
│   ├── features/         # 特徴量生成
│   ├── api/              # FastAPI
│   └── discord/          # Discord Bot
│
├── models/               # 学習済みモデル保存先
│   └── ensemble_model.pkl
│
├── scripts/
│   ├── backtest_all_bet_types.py  # バックテスト
│   └── predict_arima.py           # 時系列予測
│
└── backtest_results/     # バックテスト結果
```

## 使い方の詳細

### Discord Botコマンド

```
!predict <race_code>    # レース予想
!help                   # ヘルプ表示
```

### バックテスト

```bash
# 全馬券種別でバックテスト
python scripts/backtest_all_bet_types.py

# 特定期間のバックテスト
python -m src.models.fast_backtest --start 2024-01-01 --end 2024-12-31
```

## トラブルシューティング

### モデルが見つからない

```bash
# モデルを再学習
python -m src.models.fast_train
```

### DB接続エラー

```bash
# .envファイルを確認
cat .env

# DB接続をテスト
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT 1;"
```

## 回収率200%達成のために

- 人気薄の好走馬を見つける
- オッズと実力の乖離を狙う
- 過剰人気馬を避ける
- 期待値計算を徹底する
- バックテストで継続改善

頑張りましょう！
