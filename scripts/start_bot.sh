#!/bin/bash
# Discord Bot起動スクリプト

cd "$(dirname "$0")/.."

source venv/bin/activate

echo "======================================"
echo "Discord Botを起動します"
echo "======================================"
echo "設定: .env"
echo "======================================"

# Discord Botトークンとチャンネルが設定されているか確認
if [ -z "$DISCORD_BOT_TOKEN" ] && ! grep -q "^DISCORD_BOT_TOKEN=" .env; then
    echo "⚠️  警告: DISCORD_BOT_TOKEN が設定されていません"
    echo ""
    echo "Discord Bot Tokenの取得方法:"
    echo "1. https://discord.com/developers/applications にアクセス"
    echo "2. New Application をクリック"
    echo "3. Bot → Add Bot をクリック"
    echo "4. Token → Copy をクリック"
    echo "5. .env に DISCORD_BOT_TOKEN=<取得したトークン> を追加"
    echo ""
    echo "通知チャンネルIDの取得方法:"
    echo "1. Discordで開発者モードを有効化（設定 → 詳細設定 → 開発者モード）"
    echo "2. 通知を送りたいチャンネルを右クリック → IDをコピー"
    echo "3. .env に DISCORD_CHANNEL_ID=<取得したID> を追加"
    echo ""
    exit 1
fi

python -m src.discord.bot
