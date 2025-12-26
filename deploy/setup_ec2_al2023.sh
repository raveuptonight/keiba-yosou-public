#!/bin/bash
# EC2インスタンスセットアップスクリプト（Amazon Linux 2023用）

set -e

echo "===== 競馬予想システム EC2セットアップ (Amazon Linux 2023) ====="

# 必要なパッケージを一括インストール
echo "[1/6] 必要なパッケージを一括インストール中..."
echo "  - git, python3.11, tmux をインストールします"
sudo dnf update -y
sudo dnf install -y git python3.11 python3.11-pip python3.11-devel tmux

# PostgreSQLインストール（オプション）
echo "[2/6] PostgreSQLインストール中（オプション、スキップする場合はCtrl+C）..."
sleep 3
sudo dnf install -y postgresql15 postgresql15-server
sudo postgresql-setup --initdb
sudo systemctl enable postgresql
sudo systemctl start postgresql

# プロジェクトクローン
echo "[3/6] プロジェクトクローン中..."
cd /home/ec2-user
if [ ! -d "keiba-yosou" ]; then
    git clone https://github.com/raveuptonight/keiba-yosou.git
fi
cd keiba-yosou

# 仮想環境作成
echo "[4/6] Python仮想環境作成中..."
python3.11 -m venv venv
source venv/bin/activate

# 依存関係インストール
echo "[5/6] 依存関係インストール中..."
pip install --upgrade pip
pip install -r requirements.txt

# systemdサービス登録
echo "[6/6] systemdサービス登録中..."
sudo cp deploy/systemd/keiba-api.service /etc/systemd/system/
sudo cp deploy/systemd/keiba-bot.service /etc/systemd/system/
sudo systemctl daemon-reload

echo ""
echo "===== セットアップ完了 ====="
echo ""
echo "次のステップ:"
echo "1. .envファイルを作成・編集してください"
echo "   cp .env.example .env"
echo "   nano .env"
echo ""
echo "2. PostgreSQLデータベースを作成してください（必要な場合）"
echo "   sudo -u postgres psql"
echo "   CREATE DATABASE keiba_db;"
echo "   ALTER USER postgres WITH PASSWORD 'your_password';"
echo "   GRANT ALL PRIVILEGES ON DATABASE keiba_db TO postgres;"
echo ""
echo "3. サービスを起動してください"
echo "   sudo systemctl enable keiba-api"
echo "   sudo systemctl enable keiba-bot"
echo "   sudo systemctl start keiba-api"
echo "   sudo systemctl start keiba-bot"
echo ""
echo "4. ステータス確認"
echo "   sudo systemctl status keiba-api"
echo "   sudo systemctl status keiba-bot"
echo ""
