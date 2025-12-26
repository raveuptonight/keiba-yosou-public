#!/bin/bash
# S3からJRA-VANデータを取得（EC2実行用）

set -e

# 設定
S3_BUCKET="${S3_BUCKET:-keiba-yosou-data}"
DB_NAME="${LOCAL_DB_NAME:-keiba_db}"
DB_USER="${LOCAL_DB_USER:-ec2-user}"
COMPRESSED_FILE="latest.sql.gz"
DUMP_FILE="latest.sql"

echo "===== S3からJRA-VANデータ取得 ====="
echo "開始時刻: $(date)"

# S3からダウンロード
echo "[1/4] S3からダウンロード中..."
aws s3 cp s3://$S3_BUCKET/latest.sql.gz $COMPRESSED_FILE

# 解凍
echo "[2/4] 解凍中..."
gunzip $COMPRESSED_FILE

# PostgreSQLにリストア
echo "[3/4] PostgreSQLリストア中..."
psql -U $DB_USER -d $DB_NAME < $DUMP_FILE

# ファイル削除
echo "[4/4] クリーンアップ中..."
rm $DUMP_FILE

echo ""
echo "===== 同期完了 ====="
echo "完了時刻: $(date)"
