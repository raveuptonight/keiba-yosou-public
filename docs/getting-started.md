# Getting Started

keiba-yosoのセットアップと基本的な使い方を説明します。

## 前提条件

- Docker & Docker Compose
- Git
- JRA-VANデータが格納されたPostgreSQL（mykeibadb）

## インストール

### 1. リポジトリのクローン

```bash
git clone https://github.com/raveuptonight/keiba-yosou.git
cd keiba-yosou
```

### 2. 環境変数の設定

```bash
cp .env.example .env
```

`.env`ファイルを編集して必要な値を設定:

```ini
# 必須
DB_PASSWORD=your_password_here

# Discord Bot（オプション）
DISCORD_BOT_TOKEN=your_token_here
DISCORD_NOTIFICATION_CHANNEL_ID=your_channel_id
```

### 3. 初期セットアップ

```bash
make setup
```

これにより以下が実行されます:

1. Dockerイメージのビルド
2. コンテナの起動
3. ヘルスチェック
4. データベースマイグレーション

## 動作確認

### API確認

```bash
make health
# または
curl http://localhost:8000/health
```

### ログ確認

```bash
make logs      # 全サービス
make logs-api  # APIのみ
make logs-bot  # Discord Botのみ
```

## 基本的な使い方

### 予想の生成

```bash
curl -X POST http://localhost:8000/api/predictions/generate \
  -H "Content-Type: application/json" \
  -d '{"race_id": "2025012506010911"}'
```

### Discord Bot

Botが正常に起動していれば、Discordサーバーで以下のコマンドが使用できます:

- `/predict <レース名>` - 指定レースの予想を生成
- `/today` - 本日のレース一覧

### ダッシュボード

Streamlitダッシュボードは http://localhost:8501 で確認できます。

## モデルのトレーニング

初回または再トレーニングが必要な場合:

```bash
make train
```

!!! note
    トレーニングには10〜15分程度かかります。

## トラブルシューティング

### APIが起動しない

```bash
make logs-api
```

よくある原因:

- DBパスワードが未設定
- PostgreSQLが起動していない
- ポート8000が使用中

### Discord Botが応答しない

```bash
make logs-bot
```

チェックポイント:

- `DISCORD_BOT_TOKEN`が正しいか
- Botがサーバーに招待されているか
- 必要な権限があるか

## 次のステップ

- [API Reference](usage/api-reference.md) - APIの詳細仕様
- [Architecture](architecture/system-design.md) - システム設計の理解
