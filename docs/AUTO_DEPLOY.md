# 自動デプロイ設定

## 概要

`git pull` 実行後に自動でDiscord BotとFastAPIを再起動する仕組みです。

**仕組み**: Git post-merge hook を使用

---

## セットアップ手順（EC2側）

### 1. EC2にSSH接続

```bash
ssh ec2-user@<EC2のIPアドレス>
cd /home/ec2-user/keiba-yosou
```

### 2. 最新コードをpull

```bash
git pull
```

これで `scripts/post-merge-hook.sh` が取得されます。

### 3. Git hookをインストール

```bash
# post-merge hookを.git/hooksにコピー
cp scripts/post-merge-hook.sh .git/hooks/post-merge

# 実行権限を付与
chmod +x .git/hooks/post-merge
```

### 4. sudoersにec2-userを追加（パスワードなしでsystemctl実行可能に）

**重要**: サービス再起動にはsudo権限が必要です。

```bash
# sudoersファイルを編集
sudo visudo
```

以下の行を追加（ファイルの最後に）:

```
# keiba-yosou auto-deploy
ec2-user ALL=(ALL) NOPASSWD: /bin/systemctl restart keiba-discord-bot
ec2-user ALL=(ALL) NOPASSWD: /bin/systemctl restart keiba-api
ec2-user ALL=(ALL) NOPASSWD: /bin/systemctl status keiba-discord-bot
ec2-user ALL=(ALL) NOPASSWD: /bin/systemctl status keiba-api
```

保存して終了（`:wq`）

### 5. 動作確認

```bash
# テスト用にダミーコミットをpull（実際には何もpullされない可能性あり）
git pull

# 以下のような出力が表示されればOK:
# =========================================
# Git post-merge hook 実行
# =========================================
# ...
```

---

## 動作フロー

1. **開発者がローカルでpush**
   ```bash
   git add .
   git commit -m "機能追加"
   git push
   ```

2. **EC2でpull**
   ```bash
   cd /home/ec2-user/keiba-yosou
   git pull
   ```

3. **自動実行される処理**
   - 変更ファイルを検出
   - `requirements.txt` が変更されていたら依存パッケージを自動更新
   - Discord Bot関連ファイル（`src/discord/`, `src/services/`等）が変更されていたら `keiba-discord-bot` を再起動
   - FastAPI関連ファイル（`src/api/`, `src/services/`等）が変更されていたら `keiba-api` を再起動
   - ログ確認コマンドを表示

---

## 自動再起動の判定ロジック

### Discord Bot再起動の条件

以下のディレクトリのファイルが変更された場合:
- `src/discord/`
- `src/services/`
- `src/db/`
- `src/predict/`
- `src/betting/`

### FastAPI再起動の条件

以下のディレクトリのファイルが変更された場合:
- `src/api/`
- `src/services/`
- `src/db/`

### 依存パッケージ更新の条件

- `requirements.txt` が変更された場合、自動で `pip install -r requirements.txt` 実行

### 再起動しない場合

- ドキュメントファイルのみ変更（`.md`, `.txt`）
- スクリプトファイルのみ変更（`scripts/`）
- 設定ファイルのみ変更（`.gitignore`, `.env.example`）

---

## 実行例

### ケース1: Discord Bot関連ファイルを変更

```bash
# ローカル
git commit -m "Discord コマンド追加"
git push

# EC2
git pull
```

**出力**:
```
=========================================
Git post-merge hook 実行
時刻: 2024-12-28 15:30:00
=========================================
変更されたファイル:
src/discord/commands/prediction.py

🤖 Discord Bot関連ファイルが変更されました

=========================================
サービス再起動
=========================================
🔄 Discord Bot を再起動中...
✅ Discord Bot 再起動完了

=========================================
再起動完了
=========================================
Discord Bot ログ確認:
  sudo journalctl -u keiba-discord-bot -n 20 --no-pager
```

### ケース2: FastAPIとDiscord Botの両方を変更

```bash
# ローカル
git commit -m "サービス層を修正"
git push

# EC2
git pull
```

**出力**:
```
=========================================
Git post-merge hook 実行
=========================================
変更されたファイル:
src/services/prediction_service.py

🤖 Discord Bot関連ファイルが変更されました
🚀 FastAPI関連ファイルが変更されました

=========================================
サービス再起動
=========================================
🔄 Discord Bot を再起動中...
✅ Discord Bot 再起動完了

🔄 FastAPI を再起動中...
✅ FastAPI 再起動完了
```

### ケース3: ドキュメントのみ変更

```bash
# ローカル
git commit -m "README更新"
git push

# EC2
git pull
```

**出力**:
```
=========================================
Git post-merge hook 実行
=========================================
変更されたファイル:
README.md

ℹ️  サービス再起動は不要です（Pythonファイルの変更なし）
```

---

## トラブルシューティング

### エラー: `sudo: no tty present and no askpass program specified`

**原因**: sudoersの設定が不足

**対処法**:
```bash
sudo visudo

# 以下を追加
ec2-user ALL=(ALL) NOPASSWD: /bin/systemctl restart keiba-discord-bot
ec2-user ALL=(ALL) NOPASSWD: /bin/systemctl restart keiba-api
```

### hookが実行されない

**原因**: .git/hooks/post-merge がない、または実行権限がない

**対処法**:
```bash
# hookが存在するか確認
ls -la .git/hooks/post-merge

# なければコピー
cp scripts/post-merge-hook.sh .git/hooks/post-merge

# 実行権限を付与
chmod +x .git/hooks/post-merge
```

### サービスが再起動されない

**原因**: systemctl コマンドが失敗している

**対処法**:
```bash
# サービスが存在するか確認
systemctl status keiba-discord-bot
systemctl status keiba-api

# 手動で再起動テスト
sudo systemctl restart keiba-discord-bot
```

### 依存パッケージが更新されない

**原因**: 仮想環境が見つからない

**対処法**:
```bash
# 仮想環境が存在するか確認
ls -la venv/bin/pip

# なければ作成
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## ログ確認

### Git hook実行ログ

git pull の出力に含まれます。

### サービス再起動ログ

```bash
# Discord Bot
sudo journalctl -u keiba-discord-bot -n 50 --no-pager

# FastAPI
sudo journalctl -u keiba-api -n 50 --no-pager

# リアルタイムでログ監視
sudo journalctl -u keiba-discord-bot -f
```

---

## hookの無効化

一時的にhookを無効化したい場合:

```bash
# hookの名前を変更
mv .git/hooks/post-merge .git/hooks/post-merge.disabled

# 再度有効化
mv .git/hooks/post-merge.disabled .git/hooks/post-merge
```

---

## セキュリティ考慮事項

### sudoers設定の最小権限

`NOPASSWD` は以下の操作のみに限定:
- `systemctl restart keiba-discord-bot`
- `systemctl restart keiba-api`
- `systemctl status keiba-discord-bot`
- `systemctl status keiba-api`

他のsudo操作にはパスワードが必要なため、安全です。

### 自動実行のリスク

- **悪意あるコードのpull**: 信頼できるリポジトリのみをpullしてください
- **依存パッケージの自動更新**: requirements.txt に悪意あるパッケージが含まれる可能性
- **誤った再起動**: 変更内容を確認してからpullすることを推奨

---

## 高度な設定（オプション）

### GitHub Actions による完全自動デプロイ

**.github/workflows/deploy.yml**:

```yaml
name: Auto Deploy to EC2

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to EC2
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.EC2_HOST }}
          username: ec2-user
          key: ${{ secrets.EC2_SSH_KEY }}
          script: |
            cd /home/ec2-user/keiba-yosou
            git pull
            # post-merge hookが自動実行される
```

この設定により、GitHub に push するだけで自動的にEC2にデプロイされます。

---

## まとめ

- ✅ `git pull` で自動再起動
- ✅ 変更ファイルに応じて必要なサービスのみ再起動
- ✅ 依存パッケージの自動更新
- ✅ ログ確認コマンド表示
- ✅ ドキュメントのみ変更時は再起動なし（効率的）

**次回からの作業フロー**:

```bash
# ローカル開発
git add .
git commit -m "機能追加"
git push

# EC2デプロイ
ssh ec2-user@<EC2 IP>
cd /home/ec2-user/keiba-yosou
git pull  # これだけで自動再起動！
```
