# FastAPI セットアップガイド

## 概要

競馬予想システムのFastAPI実装が完成しました。このドキュメントでは、データダウンロード完了後にAPIを起動するまでの手順を説明します。

---

## 前提条件

- ✅ JRA-VANデータのダウンロード完了
- ✅ PostgreSQL（keiba_db）にデータが格納されている
- ✅ Python 3.11以上がインストール済み
- ✅ .envファイルが設定済み

---

## セットアップ手順

### 1. 依存パッケージのインストール

```bash
# プロジェクトルートに移動
cd /home/sakamoto/projects/keiba-yosou

# 仮想環境作成（まだの場合）
python3 -m venv venv

# 仮想環境有効化
source venv/bin/activate

# 依存パッケージインストール
pip install -r requirements.txt
```

主要パッケージ：
- **fastapi**: FastAPIフレームワーク
- **uvicorn**: ASGIサーバー
- **asyncpg**: PostgreSQL非同期ドライバ
- **pydantic**: データバリデーション
- **anthropic**: Claude API

---

### 2. 環境変数の設定

`.env`ファイルに以下の設定が必要です（`.env.example`を参考に）：

```bash
# データベース接続
DB_HOST=localhost
DB_PORT=5432
DB_NAME=keiba_db
DB_USER=postgres
DB_PASSWORD=your_password

# Claude API
ANTHROPIC_API_KEY=sk-ant-xxxxx

# FastAPI
API_HOST=0.0.0.0
API_PORT=8000
```

---

### 3. テーブル名の確認と調整

#### 3.1 実際のテーブル名を確認

```bash
psql -U postgres -d keiba_db -c "\dt"
```

#### 3.2 テーブル名マッピングを更新

実際のテーブル名が仮置きと異なる場合、`src/db/table_names.py`を編集：

```python
# 例: 実際のテーブル名が "races" の場合
TABLE_RACE: Final[str] = "races"  # 仮置き "race" から変更
```

**重要**：mykeibadbが作成したテーブル名に合わせてください。

---

### 4. データベースマイグレーション

predictionsテーブルを作成します：

```bash
psql -U postgres -d keiba_db -f src/db/migrations/001_create_predictions_table.sql
```

確認：
```bash
psql -U postgres -d keiba_db -c "\d predictions"
```

---

### 5. データベース接続テスト

```bash
python -c "
import asyncio
from src.db.async_connection import init_db_pool, test_connection, close_db_pool

async def main():
    await init_db_pool()
    result = await test_connection()
    print('✅ DB接続成功' if result else '❌ DB接続失敗')
    await close_db_pool()

asyncio.run(main())
"
```

---

### 6. FastAPI起動

#### 開発モード（自動リロード有効）

```bash
./scripts/start_api.sh
```

または：

```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 本番モード（Gunicorn使用）

```bash
gunicorn src.api.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 300
```

---

## API確認

### 1. ヘルスチェック

```bash
curl http://localhost:8000/health
```

期待される応答：
```json
{
  "status": "ok",
  "timestamp": "2024-12-28T15:00:00+09:00",
  "database": "connected",
  "claude_api": "available"
}
```

### 2. Swagger UI

ブラウザで以下にアクセス：
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 3. 今日のレース取得（例）

```bash
curl http://localhost:8000/api/v1/races/today
```

### 4. 予想生成（例）

```bash
curl -X POST http://localhost:8000/api/v1/predictions/generate \
  -H "Content-Type: application/json" \
  -d '{
    "race_id": "202412280506",
    "is_final": false,
    "total_investment": 10000
  }'
```

---

## トラブルシューティング

### DB接続エラー

**エラー**: `Database connection failed`

**対処法**：
1. PostgreSQLが起動しているか確認
   ```bash
   sudo systemctl status postgresql
   ```
2. `.env`のDB_PASSWORD が正しいか確認
3. `keiba_db`が存在するか確認
   ```bash
   psql -U postgres -l | grep keiba
   ```

### テーブルが見つからない

**エラー**: `relation "race" does not exist`

**対処法**：
1. 実際のテーブル名を確認
   ```bash
   psql -U postgres -d keiba_db -c "\dt"
   ```
2. `src/db/table_names.py`を実際のテーブル名に合わせて修正

### Claude APIエラー

**エラー**: `ANTHROPIC_API_KEY not set`

**対処法**：
1. `.env`に`ANTHROPIC_API_KEY`が設定されているか確認
2. API キーが有効か確認（https://console.anthropic.com/）

### レート制限エラー

**エラー**: `429 Too Many Requests`

**対処法**：
- Claude APIは5リクエスト/分の制限があります
- 60秒待ってから再試行してください

---

## ディレクトリ構成

```
keiba-yosou/
├── src/
│   ├── api/
│   │   ├── main.py                 # FastAPIアプリエントリーポイント
│   │   ├── exceptions.py           # カスタム例外
│   │   ├── routes/                 # エンドポイント
│   │   │   ├── races.py
│   │   │   ├── predictions.py
│   │   │   ├── horses.py
│   │   │   ├── odds.py
│   │   │   └── health.py
│   │   └── schemas/                # Pydanticスキーマ
│   │       ├── race.py
│   │       ├── prediction.py
│   │       ├── horse.py
│   │       └── odds.py
│   ├── db/
│   │   ├── async_connection.py     # 非同期DB接続
│   │   ├── table_names.py          # テーブル名マッピング
│   │   ├── queries/                # SQLクエリ
│   │   │   ├── race_queries.py
│   │   │   ├── horse_queries.py
│   │   │   ├── odds_queries.py
│   │   │   └── prediction_data.py
│   │   └── migrations/
│   │       └── 001_create_predictions_table.sql
│   └── services/
│       ├── claude_client.py        # Claude API クライアント
│       ├── prediction_service.py   # 予想生成サービス
│       └── rate_limiter.py         # レート制限
├── docs/
│   ├── API_DESIGN.md               # API設計書
│   ├── API_SETUP.md                # このファイル
│   └── PREDICTION_FORMAT.md        # 予想フォーマット仕様
├── requirements.txt                # 依存パッケージ
├── .env.example                    # 環境変数テンプレート
└── scripts/
    └── start_api.sh                # 起動スクリプト
```

---

## 次のステップ

### データダウンロード完了後の作業

1. **テーブル名の確認と調整** → `src/db/table_names.py`
2. **DB接続テスト** → `python -c "..."`
3. **API起動** → `./scripts/start_api.sh`
4. **エンドポイントテスト** → `curl http://localhost:8000/health`
5. **Discord Botとの連携テスト** → `!yosou 202412280506`

### 今後の開発予定

- ✅ FastAPI実装完了（Phase 4）
- ⏳ 実データでのテスト（データダウンロード後）
- ⏳ Discord Botとの統合テスト
- ⏳ 予想精度の検証
- ⏳ パフォーマンス最適化（インデックス調整）
- ⏳ 本番デプロイ（Neon + Render/Railway）

---

## 参考資料

- **API設計書**: `docs/API_DESIGN.md`
- **予想フォーマット**: `docs/PREDICTION_FORMAT.md`
- **ER図**: `docs/ER_DIAGRAM.md`
- **インデックス設計**: `docs/INDEX_DESIGN.md`
- **FastAPI公式ドキュメント**: https://fastapi.tiangolo.com/
- **asyncpg公式ドキュメント**: https://magicstack.github.io/asyncpg/

---

## サポート

問題が発生した場合：

1. ログを確認（FastAPIのコンソール出力）
2. DB接続を確認（`psql -U postgres -d keiba_db`）
3. テーブル名マッピングを確認（`src/db/table_names.py`）
4. GitHub Issuesで報告

---

**データダウンロード完了後、すぐに開発を再開できるよう準備完了しています！**
