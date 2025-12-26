# Amazon Linux 2023 - ワンライナーセットアップ

gitも何も入っていない真っ新なAmazon Linux 2023インスタンスから、1コマンドずつで競馬予想システムを起動する手順です。

---

## 🚀 超クイックスタート（コピペでOK）

### Step 1: パッケージ一括インストール

```bash
sudo dnf update -y && sudo dnf install -y git python3.11 python3.11-pip tmux
```

これで以下が全部入ります：
- ✅ git
- ✅ Python 3.11
- ✅ pip
- ✅ tmux

---

### Step 2: プロジェクトクローン & セットアップ

```bash
git clone https://github.com/raveuptonight/keiba-yosou.git && \
cd keiba-yosou && \
python3.11 -m venv venv && \
source venv/bin/activate && \
pip install --upgrade pip && \
pip install -r requirements.txt
```

---

### Step 3: 環境変数設定

```bash
cp .env.example .env && nano .env
```

**編集内容:**

```bash
GEMINI_API_KEY=あなたのAPIキー
DISCORD_BOT_TOKEN=あなたのBotトークン
DISCORD_CHANNEL_ID=あなたのチャンネルID
API_HOST=0.0.0.0
API_PORT=8000
API_BASE_URL=http://localhost:8000
```

保存: `Ctrl+X` → `Y` → `Enter`

---

### Step 4: 起動

#### tmuxで起動（1つのコマンド）

```bash
tmux new -s keiba -d "source ~/keiba-yosou/venv/bin/activate && cd ~/keiba-yosou && python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000" && \
tmux split-window -t keiba -v "source ~/keiba-yosou/venv/bin/activate && cd ~/keiba-yosou && python -m src.discord.bot" && \
tmux attach -t keiba
```

または手動で：

```bash
# tmuxセッション開始
tmux new -s keiba

# API起動
cd ~/keiba-yosou
source venv/bin/activate
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

新しいウィンドウ: `Ctrl+B` → `C`

```bash
# Bot起動
cd ~/keiba-yosou
source venv/bin/activate
python -m src.discord.bot
```

デタッチ: `Ctrl+B` → `D`

---

## 動作確認

```bash
# API確認
curl http://localhost:8000/

# Discord Botは!helpコマンドで確認
```

---

## 完全自動スクリプト版

```bash
# Step 1: パッケージインストール
sudo dnf update -y && sudo dnf install -y git python3.11 python3.11-pip tmux

# Step 2: セットアップスクリプト実行
cd ~
git clone https://github.com/raveuptonight/keiba-yosou.git
cd keiba-yosou
bash deploy/setup_ec2_al2023.sh

# Step 3: .env編集
cp .env.example .env
nano .env

# Step 4: 起動
tmux new -s keiba
source venv/bin/activate
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
# Ctrl+B → C
python -m src.discord.bot
# Ctrl+B → D
```

---

## トラブルシューティング

### python3.11が見つからない

```bash
# インストール確認
python3.11 --version

# なければ再インストール
sudo dnf install -y python3.11 python3.11-pip
```

### gitコマンドが見つからない

```bash
sudo dnf install -y git
```

### tmuxが使えない

```bash
sudo dnf install -y tmux
```

### 全部まとめて確認

```bash
# 必要なコマンドが全部入っているか確認
which git python3.11 tmux pip
```

---

## 最小限の手順まとめ

```bash
# 1. パッケージインストール（1行）
sudo dnf update -y && sudo dnf install -y git python3.11 python3.11-pip tmux

# 2. クローン & セットアップ（1行）
git clone https://github.com/raveuptonight/keiba-yosou.git && cd keiba-yosou && python3.11 -m venv venv && source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt

# 3. .env作成
cp .env.example .env && nano .env

# 4. tmux起動
tmux new -s keiba

# 5. API起動
source venv/bin/activate && python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 6. 新しいウィンドウ（Ctrl+B → C）
source venv/bin/activate && python -m src.discord.bot

# 7. デタッチ（Ctrl+B → D）
```

これで完了！🎉
