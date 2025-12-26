# Amazon Linux 2023 クイックスタート

EC2 (Amazon Linux 2023) で競馬予想システムを動かすための最短手順です。

---

## 前提条件

- EC2インスタンス（Amazon Linux 2023）
- SSH接続可能
- セキュリティグループでポート8000開放（API公開する場合のみ）

---

## 最短手順（5ステップ）

### 1. SSH接続

```bash
ssh -i your-key.pem ec2-user@your-ec2-ip
```

### 2. 必要なパッケージを一括インストール

```bash
# 1行で全部インストール
sudo dnf update -y && sudo dnf install -y git python3.11 python3.11-pip tmux
```

**含まれるもの:**
- `git`: リポジトリクローン用
- `python3.11`: Python 3.11本体
- `python3.11-pip`: パッケージマネージャー
- `tmux`: セッション管理（SSH切断後もプロセス継続）

### 3. プロジェクトクローン & セットアップ

```bash
# プロジェクトクローン
git clone https://github.com/raveuptonight/keiba-yosou.git
cd keiba-yosou

# 仮想環境作成
python3.11 -m venv venv

# 仮想環境有効化
source venv/bin/activate

# 依存関係インストール
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. 環境変数設定

```bash
# .envファイル作成
cp .env.example .env

# エディタで編集
nano .env
```

**必須設定項目:**

```bash
# Gemini API
GEMINI_API_KEY=あなたのGemini APIキー
GEMINI_MODEL=gemini-2.0-flash-exp

# Discord Bot
DISCORD_BOT_TOKEN=あなたのDiscord Botトークン
DISCORD_CHANNEL_ID=あなたのチャンネルID

# FastAPI
API_HOST=0.0.0.0
API_PORT=8000
API_BASE_URL=http://localhost:8000
```

保存: `Ctrl+X` → `Y` → `Enter`

### 5. 起動

#### tmuxで起動（推奨）

```bash
# tmuxセッション開始
tmux new -s keiba

# 仮想環境有効化
source venv/bin/activate

# API起動
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

新しいウィンドウを開く: `Ctrl+B` → `C`

```bash
# 仮想環境有効化
cd ~/keiba-yosou
source venv/bin/activate

# Discord Bot起動
python -m src.discord.bot
```

tmuxデタッチ（SSH切断してもプロセス継続）: `Ctrl+B` → `D`

**再接続:**
```bash
tmux attach -t keiba
```

---

## 動作確認

### APIテスト

```bash
# EC2内から
curl http://localhost:8000/
curl http://localhost:8000/health

# ローカルPCから（セキュリティグループで8000番ポート開放済みの場合）
curl http://your-ec2-ip:8000/
```

### Discord Botテスト

Discordで:
```
!help
!today
!stats
```

---

## tmuxコマンド早見表

```bash
# 新規セッション作成
tmux new -s セッション名

# セッション一覧
tmux ls

# セッションにアタッチ
tmux attach -t セッション名

# デタッチ（セッションを残してtmuxを抜ける）
Ctrl+B → D

# 新しいウィンドウ作成
Ctrl+B → C

# ウィンドウ切り替え
Ctrl+B → 0,1,2...（ウィンドウ番号）

# 前のウィンドウ
Ctrl+B → P

# 次のウィンドウ
Ctrl+B → N

# ウィンドウ一覧
Ctrl+B → W

# 現在のウィンドウを終了
exit または Ctrl+D

# セッション終了（全ウィンドウで exit）
各ウィンドウで exit
```

---

## コード更新時

```bash
# SSH接続
ssh -i your-key.pem ec2-user@your-ec2-ip

# プロジェクトディレクトリに移動
cd ~/keiba-yosou

# 最新コード取得
git pull

# 依存関係更新
source venv/bin/activate
pip install -r requirements.txt

# tmuxセッションに再接続
tmux attach -t keiba

# 各ウィンドウで Ctrl+C でプロセス停止 → 再起動
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
# または
python -m src.discord.bot
```

---

## systemdで自動起動設定（オプション）

tmuxの代わりにsystemdを使うと、EC2再起動時に自動起動します。

```bash
# サービスファイルをコピー
sudo cp deploy/systemd/keiba-api.service /etc/systemd/system/
sudo cp deploy/systemd/keiba-bot.service /etc/systemd/system/

# デーモンリロード
sudo systemctl daemon-reload

# 自動起動有効化
sudo systemctl enable keiba-api
sudo systemctl enable keiba-bot

# サービス起動
sudo systemctl start keiba-api
sudo systemctl start keiba-bot

# ステータス確認
sudo systemctl status keiba-api
sudo systemctl status keiba-bot

# ログ確認
sudo journalctl -u keiba-api -f
sudo journalctl -u keiba-bot -f
```

---

## トラブルシューティング

### Python 3.11が見つからない

```bash
# インストール確認
python3.11 --version

# インストール
sudo dnf install -y python3.11 python3.11-pip
```

### ポート8000が使用中

```bash
# プロセス確認
sudo lsof -i:8000

# プロセス終了
sudo kill -9 <PID>
```

### tmuxセッションに接続できない

```bash
# セッション一覧
tmux ls

# セッションが存在しない場合は新規作成
tmux new -s keiba
```

---

これで完了です！🚀
