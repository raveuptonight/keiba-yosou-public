# データダウンロード完了後チェックリスト

## 概要

JRA-VANデータのダウンロード完了後、以下の手順でシステムを立ち上げます。

**所要時間**: 約30分

---

## ステップ1: データ確認（5分）

### 1.1 PostgreSQL接続確認

```bash
psql -U postgres -d keiba_db -c "SELECT version();"
```

期待される結果: PostgreSQLのバージョンが表示される

### 1.2 テーブル一覧確認

```bash
psql -U postgres -d keiba_db -c "\dt"
```

期待される結果: mykeibadbが作成したテーブルが表示される（20個以上）

### 1.3 データ件数確認

```bash
cd /home/sakamoto/projects/keiba-yosou
source venv/bin/activate
python scripts/check_db_data.py
```

期待される結果:
- レース情報: 数十万件以上
- 馬情報: 数十万頭以上
- 年度別データ: 1986年〜最新年まで

---

## ステップ2: テーブル名マッピング更新（10分）

### 2.1 実際のテーブル名を確認

```bash
python scripts/check_table_names.py
```

このスクリプトが出力する対応表を確認します。

### 2.2 table_names.py を更新

`src/db/table_names.py` を実際のテーブル名に合わせて編集：

```python
# 例: mykeibadbが "n_race" という名前で作成した場合
TABLE_RACE: Final[str] = "n_race"  # 仮置き "race" から変更
```

**重要**: 27個すべてのテーブル名を確認して更新してください。

### 2.3 カラム名の確認

```bash
# 例: レーステーブルの構造確認
psql -U postgres -d keiba_db -c "\d n_race"
```

カラム名が想定と異なる場合、`src/db/table_names.py` の `COL_*` 定数も更新します。

---

## ステップ3: マイグレーション実行（2分）

### 3.1 predictionsテーブル作成

```bash
psql -U postgres -d keiba_db -f src/db/migrations/001_create_predictions_table.sql
```

### 3.2 作成確認

```bash
psql -U postgres -d keiba_db -c "\d predictions"
```

期待される結果: predictionsテーブルの構造が表示される

---

## ステップ4: 依存パッケージ確認（3分）

### 4.1 仮想環境有効化

```bash
cd /home/sakamoto/projects/keiba-yosou
source venv/bin/activate
```

### 4.2 パッケージインストール

```bash
pip install -r requirements.txt
```

### 4.3 主要パッケージ確認

```bash
pip list | grep -E "fastapi|asyncpg|anthropic|discord"
```

期待される結果:
- fastapi >= 0.115.0
- asyncpg >= 0.29.0
- anthropic >= 0.40.0
- discord.py >= 2.3.2

---

## ステップ5: 環境変数確認（2分）

### 5.1 .envファイル確認

```bash
cat .env | grep -E "DB_|ANTHROPIC_|DISCORD_"
```

必須項目:
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- `ANTHROPIC_API_KEY`
- `DISCORD_BOT_TOKEN`

### 5.2 不足があれば追加

```bash
nano .env
```

---

## ステップ6: データベース接続テスト（3分）

### 6.1 同期接続テスト（Discord Bot用）

```bash
python -c "
from src.db.connection import get_db
db = get_db()
conn = db.get_connection()
if conn:
    print('✅ 同期接続成功')
    conn.close()
else:
    print('❌ 同期接続失敗')
"
```

### 6.2 非同期接続テスト（FastAPI用）

```bash
python -c "
import asyncio
from src.db.async_connection import init_db_pool, test_connection, close_db_pool

async def main():
    await init_db_pool()
    result = await test_connection()
    print('✅ 非同期接続成功' if result else '❌ 非同期接続失敗')
    await close_db_pool()

asyncio.run(main())
"
```

---

## ステップ7: FastAPI起動テスト（5分）

### 7.1 ローカルで起動（WSL2）

```bash
./scripts/start_api.sh
```

別のターミナルで確認:

```bash
# ヘルスチェック
curl http://localhost:8000/health

# Swagger UI
# ブラウザで http://localhost:8000/docs にアクセス
```

期待される結果:
```json
{
  "status": "ok",
  "timestamp": "...",
  "database": "connected",
  "claude_api": "available"
}
```

### 7.2 今日のレース取得テスト

```bash
curl http://localhost:8000/api/v1/races/today
```

レースデータが返ってくればOK（ない日は空配列）

---

## ステップ8: Discord Bot起動テスト（3分）

### 8.1 ローカルで起動（WSL2）

```bash
python -m src.discord.bot
```

期待される結果: "Logged in as ..." が表示される

### 8.2 Discordで動作確認

Discordチャンネルで以下を試す:
- `!help` → ヘルプが表示される
- `!today` → 本日のレース一覧が表示される（データがあれば）

---

## ステップ9: 予想テスト（10分）

### 9.1 実レースで予想実行

**重要**: 予想にはClaude APIトークンを消費します（$0.03程度/回）

```bash
# Discord経由
!predict 中山1R
```

または

```bash
# API経由
curl -X POST http://localhost:8000/api/v1/predictions/generate \
  -H "Content-Type: application/json" \
  -d '{
    "race_id": "202412280101",
    "is_final": false,
    "total_investment": 10000
  }'
```

### 9.2 予想結果確認

- Discord: 予想結果がフォーマット表示される
- API: JSONレスポンスが返る

### 9.3 predictionsテーブル確認

```bash
psql -U postgres -d keiba_db -c "SELECT * FROM predictions ORDER BY predicted_at DESC LIMIT 1;"
```

予想結果が保存されていればOK

---

## トラブルシューティング

### エラー: `relation "race" does not exist`

**原因**: `src/db/table_names.py` のテーブル名が実際と異なる

**対処**:
1. `python scripts/check_table_names.py` で実際のテーブル名確認
2. `src/db/table_names.py` を修正
3. FastAPI再起動

### エラー: `Database connection failed`

**原因**: PostgreSQLが起動していない、または.envの設定が間違っている

**対処**:
```bash
# PostgreSQL起動確認
sudo systemctl status postgresql

# パスワード確認
psql -U postgres -d keiba_db -c "SELECT 1;"

# .env確認
cat .env | grep DB_PASSWORD
```

### エラー: `ANTHROPIC_API_KEY not set`

**原因**: .envにClaude APIキーが設定されていない

**対処**:
```bash
# .envに追加
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env

# FastAPI再起動
```

### エラー: `429 Too Many Requests`

**原因**: Claude APIのレート制限（5リクエスト/分）

**対処**: 60秒待ってから再試行

---

## 完了チェックリスト

- [ ] PostgreSQL接続確認
- [ ] テーブル名マッピング更新
- [ ] predictionsテーブル作成
- [ ] 依存パッケージインストール
- [ ] .env設定確認
- [ ] データベース接続テスト（同期・非同期）
- [ ] FastAPI起動成功
- [ ] ヘルスチェックOK
- [ ] Discord Bot起動成功
- [ ] 予想実行テスト成功
- [ ] predictionsテーブルにデータ保存確認

---

## 次のステップ

すべて完了したら、以下の開発タスクに進めます：

1. **予想精度の検証**
   - 過去レースで予想を実行
   - 回収率を計算
   - プロンプト改善

2. **パフォーマンス最適化**
   - クエリ実行時間計測
   - インデックス追加（INDEX_DESIGN.md参照）
   - キャッシュ導入

3. **Discord Bot機能拡張**
   - 自動予想スケジューラー（朝9時、レース1時間前）
   - 馬券購入推奨（`!baken`コマンド）
   - 統計表示（`!stats`コマンド）

4. **本番デプロイ**
   - EC2にデプロイ（systemd設定済み）
   - Neon Postgresへの移行（オプション）
   - ドメイン設定

---

## 参考資料

- **API設計書**: `docs/API_DESIGN.md`
- **ER図**: `docs/ER_DIAGRAM.md`
- **インデックス設計**: `docs/INDEX_DESIGN.md`
- **API起動手順**: `docs/API_SETUP.md`
- **ディレクトリ構造**: `docs/DIRECTORY_STRUCTURE.md`

---

**データダウンロード完了後、このチェックリストに沿って進めてください！**
