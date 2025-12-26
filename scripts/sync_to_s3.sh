#!/bin/bash
# JRA-VANデータをS3に同期（ローカル実行用）

set -e

# 設定
S3_BUCKET="${S3_BUCKET:-keiba-yosou-data}"
DB_NAME="${LOCAL_DB_NAME:-keiba_db}"
DB_USER="${LOCAL_DB_USER:-postgres}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DUMP_FILE="jravan_dump_${TIMESTAMP}.sql"
COMPRESSED_FILE="${DUMP_FILE}.gz"

echo "===== JRA-VANデータ S3同期 ====="
echo "開始時刻: $(date)"

# PostgreSQLダンプ（jravanスキーマのみ）
echo "[1/4] PostgreSQLダンプ中..."
pg_dump -U $DB_USER -d $DB_NAME -n jravan > $DUMP_FILE

# gzip圧縮
echo "[2/4] 圧縮中..."
gzip $DUMP_FILE

# S3にアップロード
echo "[3/4] S3アップロード中..."
aws s3 cp $COMPRESSED_FILE s3://$S3_BUCKET/dumps/

# 最新版としてコピー
aws s3 cp $COMPRESSED_FILE s3://$S3_BUCKET/latest.sql.gz

# ローカルファイル削除
echo "[4/4] クリーンアップ中..."
rm $COMPRESSED_FILE

echo ""
echo "===== 同期完了 ====="
echo "ファイル名: $COMPRESSED_FILE"
echo "S3パス: s3://$S3_BUCKET/latest.sql.gz"
echo "完了時刻: $(date)"
