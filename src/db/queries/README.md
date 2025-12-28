# データベースクエリモジュール

JRA-VANデータベースから効率的にデータを取得するクエリモジュール群。

## 概要

このディレクトリには、27種類のJRA-VANテーブルから必要なデータを取得するための4つの主要クエリモジュールが含まれています。

```
src/db/queries/
├── __init__.py              # モジュールエクスポート
├── race_queries.py          # レース情報取得
├── horse_queries.py         # 馬情報取得
├── odds_queries.py          # オッズ情報取得
└── prediction_data.py       # 予想データ集約（最重要）
```

## モジュール詳細

### 1. race_queries.py

レース情報を取得するクエリ群。

**主要関数**:

- `get_race_info(race_id)` - レース基本情報を取得
- `get_race_entries(race_id)` - レースの出走馬一覧を取得
- `get_races_today()` - 今日のレース一覧を取得
- `get_races_by_date(date)` - 指定日のレース一覧を取得
- `get_race_detail(race_id)` - レース詳細情報（基本情報+出走馬）を取得

**使用テーブル**: RA, SE, UM, KS, CH, O1

**使用例**:
```python
from src.db.async_connection import get_connection
from src.db.queries import get_race_detail

async with get_connection() as conn:
    detail = await get_race_detail(conn, "202412280506")
    print(f"レース名: {detail['race']['race_name']}")
    print(f"出走頭数: {detail['entry_count']}")
```

---

### 2. horse_queries.py

馬の情報（基本情報、過去成績、血統、調教）を取得するクエリ群。

**主要関数**:

- `get_horse_info(kettonum)` - 馬の基本情報を取得
- `get_horses_recent_races(kettonums, limit=10)` - 複数馬の過去N走を一括取得
- `get_horses_pedigree(kettonums)` - 複数馬の血統情報を一括取得
- `get_horses_training(kettonums, days_back=30)` - 複数馬の調教情報を一括取得
- `get_horses_statistics(race_id, kettonums)` - 複数馬の着度数統計を一括取得
- `get_horse_detail(kettonum)` - 馬の詳細情報（全データ統合）を取得

**使用テーブル**: UM, SE, RA, SK, HN, HC, WC, CK

**使用例**:
```python
from src.db.async_connection import get_connection
from src.db.queries import get_horse_detail

async with get_connection() as conn:
    detail = await get_horse_detail(conn, "2019105432", history_limit=10)
    print(f"馬名: {detail['horse_info']['bamei']}")
    print(f"過去走数: {detail['total_races']}")
    print(f"父: {detail['pedigree']['chichi_name']}")
```

**最適化ポイント**:
- 複数馬のデータを一括取得（N+1問題の回避）
- 10年以内のデータに自動フィルタ（`ML_TRAINING_YEARS_BACK`）
- 調教データは直近1ヶ月に限定

---

### 3. odds_queries.py

各種オッズデータを取得するクエリ群。

**主要関数**:

- `get_odds_win_place(race_id)` - 単勝・複勝オッズを取得
- `get_odds_quinella(race_id)` - 馬連オッズを取得
- `get_odds_exacta(race_id)` - 馬単オッズを取得
- `get_odds_wide(race_id)` - ワイドオッズを取得
- `get_odds_trio(race_id)` - 3連複オッズを取得
- `get_odds_trifecta(race_id)` - 3連単オッズを取得
- `get_odds_bracket_quinella(race_id)` - 枠連オッズを取得
- `get_race_odds(race_id, ticket_types=None)` - 全券種のオッズを一括取得

**使用テーブル**: O1, O2, O3, O4, O5, O6

**使用例**:
```python
from src.db.async_connection import get_connection
from src.db.queries import get_race_odds

async with get_connection() as conn:
    # 全券種取得
    odds = await get_race_odds(conn, "202412280506")
    print(f"1番人気単勝オッズ: {odds['win'][0]['odds']}")

    # 単勝・複勝のみ取得（軽量版）
    odds_slim = await get_race_odds(conn, "202412280506", ticket_types=["win", "place"])
```

**オッズ値の自動変換**:
- JRA-VANは10倍値で格納 → 自動的に実際のオッズ値に変換（÷10）
- 例: DB値 `35` → 返り値 `3.5`

---

### 4. prediction_data.py（最重要）

**予想生成に必要な全データを27テーブルから効率的に集約する統合クエリ**。

**主要関数**:

- `get_race_prediction_data(race_id)` - 予想用フルデータを取得
- `get_race_prediction_data_slim(race_id)` - 予想用軽量データを取得（朝予想用）
- `validate_prediction_data(data)` - データの整合性チェック
- `get_prediction_data_summary(data)` - データ完全性のサマリー生成

**データ集約フロー**:
```
1. レース基本情報取得（RA）
2. 出走馬一覧取得（SE, UM, KS, CH）
3. 各馬の過去10走取得（SE + RA）
4. 血統情報取得（SK, HN）
5. 調教情報取得（HC, WC）
6. 着度数統計取得（CK）
7. オッズ情報取得（O1-O6）
```

**使用テーブル**: 27テーブルすべて

**使用例**:
```python
from src.db.async_connection import get_connection
from src.db.queries import (
    get_race_prediction_data,
    validate_prediction_data,
    get_prediction_data_summary
)

async with get_connection() as conn:
    # 予想データ取得
    data = await get_race_prediction_data(conn, "202412280506")

    # データ整合性チェック
    validation = await validate_prediction_data(data)
    if not validation["is_valid"]:
        print(f"警告: {validation['warnings']}")

    # サマリー表示
    summary = await get_prediction_data_summary(data)
    print(f"レース名: {summary['race_name']}")
    print(f"データ完全性: 過去成績 {summary['data_completeness']['histories']:.0%}")
```

**パフォーマンス最適化**:
- 並列データ取得で高速化
- インデックス活用（INDEX_DESIGN.md参照）
- 不要なデータは取得しない（10年以内、最終オッズのみ等）

**軽量版（Slim）の違い**:

| 項目 | フル版 | 軽量版 |
|-----|-------|-------|
| 過去成績 | 10走 | 5走 |
| 調教期間 | 30日 | 14日 |
| オッズ券種 | 全券種 | 単勝・複勝のみ |
| 用途 | 最終予想 | 朝予想 |

---

## 共通仕様

### データフィルタリング

すべてのクエリで以下のフィルタが自動適用されます:

- **データ区分**: `data_kubun = '7'`（確定データのみ）
- **データ期間**: 直近10年以内（`ML_TRAINING_YEARS_BACK`）
- **オッズ**: 最終オッズのみ（`data_kubun = '3'`）

### エラーハンドリング

```python
try:
    data = await get_race_prediction_data(conn, race_id)
except ValueError as e:
    # レースが見つからない場合
    print(f"Race not found: {e}")
except Exception as e:
    # その他のDBエラー
    logger.error(f"Database error: {e}")
```

### ログ出力

すべてのクエリ関数は以下のログを出力します:

- **INFO**: 主要処理の開始・完了
- **DEBUG**: 詳細な処理ステップ
- **WARNING**: データ欠損の警告
- **ERROR**: クエリ失敗

---

## インデックス活用

以下のインデックスを活用して高速クエリを実現（詳細は `docs/INDEX_DESIGN.md` 参照）:

### race_queries.py

- `idx_ra_kaisai_date` - 開催日での検索
- `idx_ra_jyocd` - 競馬場での検索
- `idx_ra_grade` - グレード別検索
- `idx_se_race_id` - 出走馬一覧取得

### horse_queries.py

- `idx_se_kettonum` - 馬の過去成績取得
- `idx_sk_chichi` - 父馬での検索
- `idx_hc_kettonum_date` - 調教データ取得
- `idx_ck_race_id` - 着度数統計取得

### odds_queries.py

- `idx_o1_data_kubun` - 最終オッズ取得
- `idx_o2_data_kubun` - 枠連オッズ取得
- `idx_o3_data_kubun` - 馬連オッズ取得
- `idx_o6_data_kubun` - 3連単オッズ取得

---

## テスト

各クエリモジュールの動作確認:

```bash
# 接続テスト
python -c "
import asyncio
from src.db.async_connection import init_db_pool, test_connection, close_db_pool

async def main():
    await init_db_pool()
    result = await test_connection()
    print('DB接続OK' if result else 'DB接続NG')
    await close_db_pool()

asyncio.run(main())
"

# クエリテスト（実装後）
pytest tests/db/test_queries.py -v
```

---

## パフォーマンス目標

| クエリ | 目標レスポンスタイム | 備考 |
|-------|------------------|------|
| `get_race_info()` | < 10ms | 主キー検索 |
| `get_race_entries()` | < 50ms | JOIN 4テーブル |
| `get_horses_recent_races()` | < 100ms | 10頭×10走 |
| `get_horses_pedigree()` | < 80ms | 10頭×6代血統 |
| `get_race_prediction_data()` | < 500ms | 全データ集約 |

---

## 次のステップ

1. FastAPI統合（`src/api/routes/`）
2. Discord Bot統合（`src/discord/`）
3. LLM予想サービス統合（`src/services/prediction_service.py`）

---

## 関連ドキュメント

- [API_DESIGN.md](../../../docs/API_DESIGN.md) - API設計とSQLクエリ例
- [INDEX_DESIGN.md](../../../docs/INDEX_DESIGN.md) - インデックス設計とパフォーマンス
- [ER_DIAGRAM.md](../../../docs/ER_DIAGRAM.md) - テーブル関連図
- [JRA_VAN_SPEC.md](../../../docs/JRA_VAN_SPEC.md) - JRA-VANデータ仕様
