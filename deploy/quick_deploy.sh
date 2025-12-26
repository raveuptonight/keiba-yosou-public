#!/bin/bash
# クイックデプロイスクリプト（コード更新時用）
# Amazon Linux 2023 / Ubuntu 両対応

set -e

echo "===== 競馬予想システム クイックデプロイ ====="

# プロジェクトディレクトリに移動
# Amazon Linux 2023の場合
if [ -d "/home/ec2-user/keiba-yosou" ]; then
    cd /home/ec2-user/keiba-yosou
# Ubuntuの場合
elif [ -d "/home/ubuntu/keiba-yosou" ]; then
    cd /home/ubuntu/keiba-yosou
else
    echo "Error: プロジェクトディレクトリが見つかりません"
    exit 1
fi

# 最新コードを取得
echo "[1/4] 最新コードを取得中..."
git pull

# 依存関係更新
echo "[2/4] 依存関係更新中..."
source venv/bin/activate
pip install -r requirements.txt

# サービス再起動
echo "[3/4] サービス再起動中..."
sudo systemctl restart keiba-api
sudo systemctl restart keiba-bot

# ステータス確認
echo "[4/4] ステータス確認中..."
sleep 2
sudo systemctl status keiba-api --no-pager
sudo systemctl status keiba-bot --no-pager

echo ""
echo "===== デプロイ完了 ====="
echo ""
echo "ログ確認:"
echo "  sudo journalctl -u keiba-api -f"
echo "  sudo journalctl -u keiba-bot -f"
echo ""
