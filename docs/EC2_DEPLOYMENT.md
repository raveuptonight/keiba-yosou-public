# EC2デプロイ手順書

## 前提条件

- AWS EC2インスタンス（Ubuntu 22.04 LTS）
- セキュリティグループで以下のポートを開放:
  - 22 (SSH)
  - 8000 (FastAPI) ※必要に応じて
- Elastic IP割り当て（推奨）

---

## 1. EC2インスタンス作成

### 推奨スペック

- **インスタンスタイプ**: t3.small 以上
  - vCPU: 2
  - メモリ: 2GB
  - ストレージ: 20GB
- **OS**: Ubuntu 22.04 LTS
- **セキュリティグループ**:
  - SSH (22): 自分のIPのみ
  - HTTP (8000): 必要に応じて

### セキュリティグループ設定

```
インバウンドルール:
- タイプ: SSH, ポート: 22, ソース: マイIP
- タイプ: カスタムTCP, ポート: 8000, ソース: 0.0.0.0/0 (API公開する場合)
```

---

## 2. SSH接続

```bash
# ローカルからEC2に接続
ssh -i your-key.pem ubuntu@your-ec2-ip
```

---

## 3. 自動セットアップ

```bash
# リポジトリをクローン
git clone https://github.com/raveuptonight/keiba-yosou.git
cd keiba-yosou

# セットアップスクリプト実行
bash deploy/setup_ec2.sh
```

このスクリプトで以下が自動実行されます：
- システムパッケージ更新
- Python 3.11インストール
- PostgreSQLインストール
- 依存関係インストール
- systemdサービス登録

---

## 4. 環境変数設定

```bash
# .envファイルを作成
cp .env.example .env
nano .env
```

### 設定項目

```bash
# PostgreSQL
LOCAL_DB_HOST=localhost
LOCAL_DB_PORT=5432
LOCAL_DB_NAME=keiba_db
LOCAL_DB_USER=postgres
LOCAL_DB_PASSWORD=your_secure_password

# Gemini API
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.0-flash-exp

# Discord Bot
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_CHANNEL_ID=your_channel_id

# FastAPI
API_HOST=0.0.0.0
API_PORT=8000
API_BASE_URL=http://your-ec2-ip:8000
```

---

## 5. PostgreSQLデータベース初期化

```bash
# PostgreSQLにログイン
sudo -u postgres psql

# データベース作成
CREATE DATABASE keiba_db;

# パスワード設定
ALTER USER postgres WITH PASSWORD 'your_secure_password';

# 権限付与
GRANT ALL PRIVILEGES ON DATABASE keiba_db TO postgres;

# 終了
\q
```

### スキーマ作成

```bash
# 仮想環境を有効化
source venv/bin/activate

# スキーマ作成スクリプト実行（作成する場合）
# python scripts/init_db.py
```

---

## 6. サービス起動

### サービス有効化 & 起動

```bash
# サービス有効化（自動起動設定）
sudo systemctl enable keiba-api
sudo systemctl enable keiba-bot

# サービス起動
sudo systemctl start keiba-api
sudo systemctl start keiba-bot
```

### ステータス確認

```bash
# APIサーバー
sudo systemctl status keiba-api

# Discord Bot
sudo systemctl status keiba-bot
```

### ログ確認

```bash
# リアルタイムログ
sudo journalctl -u keiba-api -f
sudo journalctl -u keiba-bot -f

# 最新100行
sudo journalctl -u keiba-api -n 100
sudo journalctl -u keiba-bot -n 100
```

---

## 7. 動作確認

### APIエンドポイントテスト

```bash
# ルートエンドポイント
curl http://localhost:8000/

# ヘルスチェック
curl http://localhost:8000/health

# API Docs（ブラウザ）
http://your-ec2-ip:8000/docs
```

### Discord Botテスト

Discordで以下のコマンドを実行：

```
!help
!today
!stats
```

---

## 8. サービス管理コマンド

### 起動・停止・再起動

```bash
# 起動
sudo systemctl start keiba-api
sudo systemctl start keiba-bot

# 停止
sudo systemctl stop keiba-api
sudo systemctl stop keiba-bot

# 再起動
sudo systemctl restart keiba-api
sudo systemctl restart keiba-bot

# 自動起動有効化
sudo systemctl enable keiba-api
sudo systemctl enable keiba-bot

# 自動起動無効化
sudo systemctl disable keiba-api
sudo systemctl disable keiba-bot
```

### コード更新時

```bash
# 最新コードを取得
cd /home/ubuntu/keiba-yosou
git pull

# 依存関係更新
source venv/bin/activate
pip install -r requirements.txt

# サービス再起動
sudo systemctl restart keiba-api
sudo systemctl restart keiba-bot
```

---

## 9. トラブルシューティング

### サービスが起動しない

```bash
# ログ確認
sudo journalctl -u keiba-api -n 100
sudo journalctl -u keiba-bot -n 100

# .envファイル確認
cat /home/ubuntu/keiba-yosou/.env

# 手動起動でエラー確認
cd /home/ubuntu/keiba-yosou
source venv/bin/activate
python -m src.discord.bot
```

### ポート8000が使用中

```bash
# ポート使用状況確認
sudo lsof -i:8000

# プロセス終了
sudo kill -9 <PID>
```

### PostgreSQL接続エラー

```bash
# PostgreSQL起動確認
sudo systemctl status postgresql

# 接続テスト
psql -U postgres -d keiba_db -h localhost
```

---

## 10. セキュリティ設定（推奨）

### ファイアウォール設定

```bash
# ufwインストール
sudo apt install ufw

# デフォルト拒否
sudo ufw default deny incoming
sudo ufw default allow outgoing

# SSH許可
sudo ufw allow ssh

# 必要に応じてAPI許可
# sudo ufw allow 8000/tcp

# 有効化
sudo ufw enable
```

### .envファイルの権限設定

```bash
# 所有者のみ読み書き可能
chmod 600 /home/ubuntu/keiba-yosou/.env
```

---

## 11. 監視・運用

### systemd タイマーで定期実行（オプション）

```bash
# 毎日特定時刻に予想実行など
# systemd timerを使用
```

### ログローテーション

systemdが自動的にログローテーションを行います。

---

## 12. バックアップ

### データベースバックアップ

```bash
# バックアップ
pg_dump -U postgres keiba_db > backup_$(date +%Y%m%d).sql

# リストア
psql -U postgres keiba_db < backup_20241226.sql
```

---

## まとめ

これでEC2上でDiscord Bot + FastAPIが常時稼働します！

**確認項目:**
- ✅ EC2インスタンス起動
- ✅ セットアップスクリプト実行
- ✅ .env設定
- ✅ PostgreSQL初期化
- ✅ サービス起動
- ✅ Discord Botコマンドテスト
- ✅ API動作確認

何か問題があれば、ログを確認してトラブルシューティングセクションを参照してください。
