#!/bin/bash
# Git post-merge hookセットアップスクリプト
#
# EC2側で実行して、自動デプロイを有効化します

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "========================================="
echo "Git post-merge hook セットアップ"
echo "========================================="

# 1. hookスクリプトの存在確認
HOOK_SCRIPT="$PROJECT_ROOT/scripts/post-merge-hook.sh"
if [ ! -f "$HOOK_SCRIPT" ]; then
    echo "❌ エラー: $HOOK_SCRIPT が見つかりません"
    echo "   git pull で最新コードを取得してください"
    exit 1
fi

# 2. .git/hooks ディレクトリの存在確認
GIT_HOOKS_DIR="$PROJECT_ROOT/.git/hooks"
if [ ! -d "$GIT_HOOKS_DIR" ]; then
    echo "❌ エラー: .git/hooks ディレクトリが見つかりません"
    echo "   Gitリポジトリのルートで実行してください"
    exit 1
fi

# 3. post-merge hookをコピー
POST_MERGE_HOOK="$GIT_HOOKS_DIR/post-merge"

if [ -f "$POST_MERGE_HOOK" ]; then
    echo "⚠️  既存のpost-merge hookが見つかりました"
    echo "   バックアップを作成します: $POST_MERGE_HOOK.backup"
    cp "$POST_MERGE_HOOK" "$POST_MERGE_HOOK.backup"
fi

cp "$HOOK_SCRIPT" "$POST_MERGE_HOOK"
chmod +x "$POST_MERGE_HOOK"

echo "✅ post-merge hook をインストールしました"
echo "   場所: $POST_MERGE_HOOK"
echo ""

# 4. sudoers設定の確認
echo "========================================="
echo "sudoers 設定確認"
echo "========================================="

# systemctl が sudo で実行可能かテスト
if sudo -n systemctl status keiba-discord-bot >/dev/null 2>&1 || sudo -n systemctl status keiba-api >/dev/null 2>&1; then
    echo "✅ sudoers 設定済み（パスワードなしでsystemctl実行可能）"
else
    echo "⚠️  sudoers 設定が必要です"
    echo ""
    echo "以下のコマンドを実行してください:"
    echo ""
    echo "  sudo visudo"
    echo ""
    echo "そして、ファイルの最後に以下を追加:"
    echo ""
    echo "  # keiba-yosou auto-deploy"
    echo "  $(whoami) ALL=(ALL) NOPASSWD: /bin/systemctl restart keiba-discord-bot"
    echo "  $(whoami) ALL=(ALL) NOPASSWD: /bin/systemctl restart keiba-api"
    echo "  $(whoami) ALL=(ALL) NOPASSWD: /bin/systemctl status keiba-discord-bot"
    echo "  $(whoami) ALL=(ALL) NOPASSWD: /bin/systemctl status keiba-api"
    echo ""
    echo "保存して終了（:wq）してから、再度このスクリプトを実行してください"
    echo ""
fi

# 5. セットアップ完了
echo ""
echo "========================================="
echo "セットアップ完了"
echo "========================================="
echo ""
echo "次回から git pull 実行時に自動的にサービスが再起動されます。"
echo ""
echo "テスト方法:"
echo "  1. ローカルで変更をpush"
echo "  2. EC2で git pull"
echo "  3. 自動再起動メッセージが表示されるか確認"
echo ""
echo "詳細は docs/AUTO_DEPLOY.md を参照してください"
echo ""
