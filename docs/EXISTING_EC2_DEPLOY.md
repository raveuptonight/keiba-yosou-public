# 既存EC2サーバーへのデプロイ手順

既にEC2サーバーがある場合の簡易デプロイ手順です。

---

## 前提条件

- 既存のEC2インスタンスにSSH接続可能
- **Amazon Linux 2023** 想定
- Python 3.11+ がインストール済み（または `dnf install python3.11` でインストール）
- PostgreSQLがインストール済み（オプション、なくてもOK）

---

## クイックスタート

### 1. SSH接続

```bash
# Amazon Linux 2023の場合はec2-user
ssh -i your-key.pem ec2-user@your-ec2-ip
```

### 2. プロジェクトをクローン

```bash
cd ~
git clone https://github.com/raveuptonight/keiba-yosou.git
cd keiba-yosou
```

### 3. 仮想環境作成 & 依存関係インストール

```bash
# Python 3.11で仮想環境作成
python3.11 -m venv venv

# 仮想環境を有効化
source venv/bin/activate

# 依存関係インストール
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. 環境変数設定

```bash
# .envファイルを作成
cp .env.example .env
nano .env  # またはvi .env
```

**必須設定項目:**

```bash
# Gemini API
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.0-flash-exp

# Discord Bot
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_CHANNEL_ID=your_channel_id

# FastAPI
API_HOST=0.0.0.0
API_PORT=8000
API_BASE_URL=http://localhost:8000

# PostgreSQL（使う場合のみ）
LOCAL_DB_HOST=localhost
LOCAL_DB_PORT=5432
LOCAL_DB_NAME=keiba_db
LOCAL_DB_USER=postgres
LOCAL_DB_PASSWORD=your_password
```

保存して終了: `Ctrl+X` → `Y` → `Enter`

---

## 起動方法

### オプション1: tmuxで起動（推奨）

tmuxを使えば、SSH切断後もプロセスが継続します。

```bash
# tmuxインストール（未インストールの場合）
# Amazon Linux 2023
sudo dnf install tmux

# Ubuntu
# sudo apt install tmux

# tmuxセッション開始
tmux new -s keiba

# 仮想環境有効化
cd ~/keiba-yosou
source venv/bin/activate

# API起動（ウィンドウ1）
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 新しいウィンドウを開く: Ctrl+B → C

# Discord Bot起動（ウィンドウ2）
cd ~/keiba-yosou
source venv/bin/activate
python -m src.discord.bot

# tmuxデタッチ（セッションを残してSSH切断）: Ctrl+B → D

# 後で再接続
tmux attach -t keiba
```

### オプション2: systemdで起動（自動起動設定）

#### systemdサービスファイルを配置

```bash
# サービスファイルをコピー（パスを修正）
sudo cp deploy/systemd/keiba-api.service /etc/systemd/system/
sudo cp deploy/systemd/keiba-bot.service /etc/systemd/system/

# サービスファイルを編集（ユーザー名とパスを確認）
sudo nano /etc/systemd/system/keiba-api.service
```

**修正箇所:**
- `User=ubuntu` → 実際のユーザー名
- `Group=ubuntu` → 実際のグループ名
- `/home/ubuntu/keiba-yosou` → 実際のパス

同様に `keiba-bot.service` も編集。

#### サービス起動

```bash
# デーモンをリロード
sudo systemctl daemon-reload

# サービス有効化（自動起動）
sudo systemctl enable keiba-api
sudo systemctl enable keiba-bot

# サービス起動
sudo systemctl start keiba-api
sudo systemctl start keiba-bot

# ステータス確認
sudo systemctl status keiba-api
sudo systemctl status keiba-bot
```

### オプション3: screenで起動

```bash
# screenインストール
# Amazon Linux 2023
sudo dnf install screen

# Ubuntu
# sudo apt install screen

# screen起動
screen -S keiba-api

# API起動
cd ~/keiba-yosou
source venv/bin/activate
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# デタッチ: Ctrl+A → D

# 新しいscreen（Bot用）
screen -S keiba-bot
cd ~/keiba-yosou
source venv/bin/activate
python -m src.discord.bot

# デタッチ: Ctrl+A → D

# 再接続
screen -r keiba-api
screen -r keiba-bot
```

---

## 動作確認

### APIテスト

```bash
# EC2内から
curl http://localhost:8000/
curl http://localhost:8000/health

# ローカルから（セキュリティグループで8000番ポート開放済みの場合）
curl http://your-ec2-ip:8000/
```

### Discord Botテスト

Discordで以下のコマンドを実行：

```
!help
!today
!stats
```

---

## コード更新時

```bash
# SSH接続
ssh -i your-key.pem ubuntu@your-ec2-ip

# プロジェクトディレクトリに移動
cd ~/keiba-yosou

# 最新コード取得
git pull

# 依存関係更新
source venv/bin/activate
pip install -r requirements.txt
```

### tmux使用の場合

```bash
# tmuxセッションに接続
tmux attach -t keiba

# ウィンドウを切り替え（Ctrl+B → 番号）
# 各ウィンドウで Ctrl+C でプロセス停止
# 再起動
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
# または
python -m src.discord.bot
```

### systemd使用の場合

```bash
# サービス再起動
sudo systemctl restart keiba-api
sudo systemctl restart keiba-bot

# ログ確認
sudo journalctl -u keiba-api -f
sudo journalctl -u keiba-bot -f
```

---

## トラブルシューティング

### ポートが使用中

```bash
# プロセス確認
sudo lsof -i:8000

# プロセス終了
sudo kill -9 <PID>
```

### Python 3.11がない

```bash
# Amazon Linux 2023の場合
sudo dnf update
sudo dnf install python3.11 python3.11-pip

# Ubuntuの場合
# sudo apt update
# sudo apt install python3.11 python3.11-venv python3.11-dev
```

### tmux/screenセッションが見つからない

```bash
# 全セッション表示
tmux ls
screen -ls

# 新しいセッション作成
tmux new -s keiba
screen -S keiba-api
```

---

## 推奨: セキュリティグループ設定

- **SSH (22)**: 自分のIPのみ許可
- **HTTP (8000)**: 必要に応じて公開（Discord Botのみなら不要）

---

## まとめ

**最小手順:**
1. `git clone`
2. `python3.11 -m venv venv`
3. `source venv/bin/activate && pip install -r requirements.txt`
4. `.env` 作成・編集
5. `tmux` でAPI + Bot起動

これで完了です！🚀
