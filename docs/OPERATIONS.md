# 本番運用ガイド

EC2での本番運用に必要なエラーハンドリング、ログ監視、定期実行、バックアップの設定方法。

---

## 1. エラーハンドリング

### アプリケーションレベル

既に実装済みのエラーハンドリング：

- **Discord Bot**: `src/discord/bot.py` の `on_command_error`
- **FastAPI**: 各エンドポイントでtry-except

### システムレベル

**systemdの自動再起動:**

```ini
# /etc/systemd/system/keiba-api.service
[Service]
Restart=always
RestartSec=10
```

- サービスが落ちたら10秒後に自動再起動
- 既に設定済み

---

## 2. ログ監視設定

### ログの確認方法

```bash
# リアルタイムログ
sudo journalctl -u keiba-api -f
sudo journalctl -u keiba-bot -f

# 最新100行
sudo journalctl -u keiba-api -n 100
sudo journalctl -u keiba-bot -n 100

# エラーのみ
sudo journalctl -u keiba-api -p err
sudo journalctl -u keiba-bot -p err

# 特定期間
sudo journalctl -u keiba-api --since "2024-12-26 00:00:00" --until "2024-12-26 23:59:59"
```

### ログローテーション

journaldが自動的にローテーション（設定不要）

**デフォルト設定:**
- 最大容量: 10%のディスク容量
- 保持期間: 制限なし（容量に依存）

**カスタマイズ（オプション）:**

```bash
# /etc/systemd/journald.conf
[Journal]
SystemMaxUse=500M
MaxRetentionSec=7day
```

### ログ検索

```bash
# "error"を含む行
sudo journalctl -u keiba-api | grep -i error

# JSONログの整形
sudo journalctl -u keiba-api -o json-pretty
```

---

## 3. 手動実行（データ同期・バックアップ）

### データ同期（基本は手動）

**ローカル（Windows/WSL）→ S3:**

```bash
cd ~/keiba-yosou
./scripts/sync_to_s3.sh
```

**S3 → EC2:**

```bash
cd ~/keiba-yosou
./scripts/sync_from_s3.sh
```

### 予想結果バックアップ（手動）

```bash
cd ~/keiba-yosou
./scripts/backup_predictions.sh
```

---

## 4. 定期実行（オプション・自動化したい場合）

**基本は手動実行を推奨しますが、自動化したい場合は以下を参考にしてください。**

### cron（シンプル）

```bash
# crontab編集
crontab -e

# 例: 毎日朝6時にS3からデータ取得
0 6 * * * /home/ec2-user/keiba-yosou/scripts/sync_from_s3.sh >> /var/log/keiba-sync.log 2>&1

# 例: 毎日深夜2時にバックアップ
0 2 * * * /home/ec2-user/keiba-yosou/scripts/backup_predictions.sh >> /var/log/keiba-backup.log 2>&1

# 確認
crontab -l
```

### Windows タスクスケジューラ（ローカル）

1. タスクスケジューラを開く
2. 「基本タスクの作成」
3. トリガー: 任意の時刻
4. 操作: プログラムの開始
   - プログラム: `C:\Windows\System32\wsl.exe`
   - 引数: `bash /home/YOUR_USER/keiba-yosou/scripts/sync_to_s3.sh`

---

## 5. バックアップ設定

### 予想結果のバックアップ（手動）

```bash
cd ~/keiba-yosou
./scripts/backup_predictions.sh
```

**バックアップ先:**
- S3: `s3://keiba-yosou-data/backups/predictions/`

**実行タイミング:**
- 週1回程度
- 重要な予想実行後

### バックアップからのリストア

```bash
# S3から特定のバックアップを取得
aws s3 cp s3://keiba-yosou-data/backups/predictions/predictions_backup_20241226_020000.sql.gz .

# 解凍
gunzip predictions_backup_20241226_020000.sql.gz

# リストア
psql -U ec2-user -d keiba_db < predictions_backup_20241226_020000.sql

# クリーンアップ
rm predictions_backup_20241226_020000.sql
```

---

## 6. 監視・アラート

### ヘルスチェック

```bash
# APIヘルスチェック
curl http://localhost:8000/health

# サービスステータス
sudo systemctl status keiba-api
sudo systemctl status keiba-bot
```

### Discord通知（エラー発生時）

今後実装予定:

```python
# エラー時にDiscord通知
async def notify_error(error_message):
    await bot.send_notification(f"❌ エラー発生: {error_message}")
```

### CloudWatch Logs（オプション）

```bash
# CloudWatch Logsエージェントインストール
sudo dnf install -y amazon-cloudwatch-agent

# 設定ファイル作成
# journaldログをCloudWatchに転送
```

---

## 7. トラブルシューティング

### サービスが起動しない

```bash
# ログ確認
sudo journalctl -u keiba-api -n 100
sudo journalctl -u keiba-bot -n 100

# .env確認
cat /home/ec2-user/keiba-yosou/.env

# 手動起動でエラー確認
cd ~/keiba-yosou
source venv/bin/activate
python -m src.discord.bot
```

### データ同期が失敗する

```bash
# AWS CLIの認証確認
aws s3 ls s3://keiba-yosou-data/

# IAMロール確認（EC2の場合）
aws sts get-caller-identity

# 手動実行でエラー確認
./scripts/sync_from_s3.sh
```

### ディスク容量不足

```bash
# ディスク使用状況確認
df -h

# ログサイズ確認
sudo journalctl --disk-usage

# 古いログ削除
sudo journalctl --vacuum-time=7d
sudo journalctl --vacuum-size=500M
```

---

## 8. 定期メンテナンス

### 週次

- [ ] ログ確認（エラーがないか）
- [ ] サービスステータス確認
- [ ] ディスク容量確認

### 月次

- [ ] バックアップの整合性確認
- [ ] 依存関係更新（セキュリティパッチ）

```bash
# システムアップデート
sudo dnf update -y

# Python依存関係更新
cd ~/keiba-yosou
source venv/bin/activate
pip list --outdated
pip install --upgrade <package>

# サービス再起動
sudo systemctl restart keiba-api
sudo systemctl restart keiba-bot
```

---

## 9. チェックリスト

### 初回セットアップ

- [ ] S3バケット作成
- [ ] IAMロール設定
- [ ] systemd timer設定
- [ ] 初回バックアップ実行
- [ ] ログ確認

### 日次確認

- [ ] Discord Bot稼働確認（!helpコマンド）
- [ ] API稼働確認（curl http://localhost:8000/health）

### 週次確認

- [ ] ログにエラーがないか確認
- [ ] ディスク容量確認（df -h）
- [ ] バックアップ確認（S3）

---

## まとめ

これで本番運用に必要な設定が完了です！

**設定済み:**
- ✅ エラーハンドリング（自動再起動）
- ✅ ログ監視（journald）
- ✅ バックアップスクリプト（手動実行）
- ✅ データ同期スクリプト（手動実行）

**運用フロー（手動）:**
1. ローカル: JRA-VANデータ更新 → `./scripts/sync_to_s3.sh`（必要な時）
2. EC2: `./scripts/sync_from_s3.sh`（データ取得が必要な時）
3. EC2: `./scripts/backup_predictions.sh`（週1回程度）
4. 定期確認: ログ・ステータス確認
