#!/bin/bash
# Git post-merge hook
# git pull 完了後に自動実行される

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "========================================="
echo "Git post-merge hook 実行"
echo "時刻: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================="

# 変更されたファイルを確認
CHANGED_FILES=$(git diff-tree -r --name-only --no-commit-id ORIG_HEAD HEAD)

echo "変更されたファイル:"
echo "$CHANGED_FILES"
echo ""

# Pythonファイルが変更されたかチェック
PYTHON_CHANGED=$(echo "$CHANGED_FILES" | grep -E '\.py$' || true)
REQUIREMENTS_CHANGED=$(echo "$CHANGED_FILES" | grep 'requirements.txt' || true)
ENV_EXAMPLE_CHANGED=$(echo "$CHANGED_FILES" | grep '.env.example' || true)

# requirements.txt が変更されていたら依存パッケージを更新
if [ -n "$REQUIREMENTS_CHANGED" ]; then
    echo "📦 requirements.txt が変更されました。依存パッケージを更新します..."
    if [ -f "$PROJECT_ROOT/venv/bin/pip" ]; then
        "$PROJECT_ROOT/venv/bin/pip" install -r "$PROJECT_ROOT/requirements.txt" --quiet
        echo "✅ 依存パッケージ更新完了"
    else
        echo "⚠️  仮想環境が見つかりません"
    fi
    echo ""
fi

# .env.example が変更されていたら警告
if [ -n "$ENV_EXAMPLE_CHANGED" ]; then
    echo "⚠️  .env.example が変更されました。"
    echo "   .env ファイルに新しい環境変数が必要かもしれません。"
    echo "   diff .env.example .env で確認してください。"
    echo ""
fi

# Discord Bot関連ファイルが変更されたかチェック
DISCORD_CHANGED=$(echo "$CHANGED_FILES" | grep -E '^src/(discord|services|db|predict|betting)/' || true)

# FastAPI関連ファイルが変更されたかチェック
API_CHANGED=$(echo "$CHANGED_FILES" | grep -E '^src/(api|services|db)/' || true)

# サービス再起動フラグ
RESTART_BOT=false
RESTART_API=false

# Discord Bot再起動が必要か判定
if [ -n "$DISCORD_CHANGED" ]; then
    echo "🤖 Discord Bot関連ファイルが変更されました"
    RESTART_BOT=true
fi

# FastAPI再起動が必要か判定
if [ -n "$API_CHANGED" ]; then
    echo "🚀 FastAPI関連ファイルが変更されました"
    RESTART_API=true
fi

# サービス再起動
if [ "$RESTART_BOT" = true ] || [ "$RESTART_API" = true ]; then
    echo ""
    echo "========================================="
    echo "サービス再起動"
    echo "========================================="

    if [ "$RESTART_BOT" = true ]; then
        echo "🔄 Discord Bot を再起動中..."
        if systemctl is-active --quiet keiba-discord-bot 2>/dev/null; then
            sudo systemctl restart keiba-discord-bot
            echo "✅ Discord Bot 再起動完了"
        else
            echo "⚠️  keiba-discord-bot サービスが見つかりません（ローカル環境の可能性）"
        fi
        echo ""
    fi

    if [ "$RESTART_API" = true ]; then
        echo "🔄 FastAPI を再起動中..."
        if systemctl is-active --quiet keiba-api 2>/dev/null; then
            sudo systemctl restart keiba-api
            echo "✅ FastAPI 再起動完了"
        else
            echo "⚠️  keiba-api サービスが見つかりません（ローカル環境の可能性）"
        fi
        echo ""
    fi

    echo "========================================="
    echo "再起動完了"
    echo "========================================="

    # ログ確認コマンドを表示
    if [ "$RESTART_BOT" = true ]; then
        echo "Discord Bot ログ確認:"
        echo "  sudo journalctl -u keiba-discord-bot -n 20 --no-pager"
        echo ""
    fi

    if [ "$RESTART_API" = true ]; then
        echo "FastAPI ログ確認:"
        echo "  sudo journalctl -u keiba-api -n 20 --no-pager"
        echo ""
    fi
else
    echo "ℹ️  サービス再起動は不要です（Pythonファイルの変更なし）"
fi

echo ""
echo "========================================="
echo "post-merge hook 完了"
echo "========================================="
