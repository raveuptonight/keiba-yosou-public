# データ期間フィルタリング仕様

## 概要

データベースには全期間（1986年〜現在）のデータを保存しますが、**機械学習の訓練と予測には直近10年分のみ使用**します。

---

## 設定値

`src/config.py` で定義：

```python
ML_TRAINING_YEARS_BACK: Final[int] = 10  # 直近10年分のデータを使用
PREDICTION_REFERENCE_YEARS: Final[int] = 5  # 直近5年分を主に参照
STATS_MAX_YEARS_BACK: Final[int] = 10  # 最大10年分の統計を集計
```

---

## SQLクエリ例

### 1. **訓練データ取得（10年分）**

```sql
-- 機械学習の訓練用データ
SELECT
    r.race_id,
    r.race_date,
    r.race_name,
    r.venue,
    h.horse_id,
    h.horse_name,
    j.jockey_id,
    j.jockey_name,
    r.finish_position,
    r.odds
FROM race r
JOIN horse h ON r.horse_id = h.horse_id
JOIN jockey j ON r.jockey_id = j.jockey_id
WHERE r.race_date >= CURRENT_DATE - INTERVAL '10 years'  -- ← 期間フィルター
  AND r.race_date < CURRENT_DATE
  AND r.finish_position IS NOT NULL  -- 結果が確定しているレースのみ
ORDER BY r.race_date DESC;
```

### 2. **馬の過去成績取得（5年分）**

```sql
-- 特定の馬の直近5年分の成績
SELECT
    race_date,
    race_name,
    finish_position,
    odds,
    prize_money
FROM race
WHERE horse_id = :horse_id
  AND race_date >= CURRENT_DATE - INTERVAL '5 years'  -- ← 期間フィルター
  AND race_date < :target_race_date  -- 予想対象レースより前
ORDER BY race_date DESC
LIMIT 20;  -- 最大20レース分
```

### 3. **騎手の勝率計算（5年分）**

```sql
-- 騎手の直近5年間の勝率
SELECT
    jockey_id,
    jockey_name,
    COUNT(*) as total_races,
    SUM(CASE WHEN finish_position = 1 THEN 1 ELSE 0 END) as wins,
    ROUND(
        SUM(CASE WHEN finish_position = 1 THEN 1 ELSE 0 END)::NUMERIC / COUNT(*) * 100,
        2
    ) as win_rate
FROM race
WHERE jockey_id = :jockey_id
  AND race_date >= CURRENT_DATE - INTERVAL '5 years'  -- ← 期間フィルター
  AND race_date < CURRENT_DATE
  AND finish_position IS NOT NULL
GROUP BY jockey_id, jockey_name;
```

### 4. **統計情報（10年分）**

```sql
-- システム全体の予想精度（直近10年）
SELECT
    COUNT(*) as total_predictions,
    AVG(actual_roi) as avg_roi,
    SUM(CASE WHEN actual_roi > 1.0 THEN 1 ELSE 0 END) as profitable_races,
    ROUND(
        SUM(CASE WHEN actual_roi > 1.0 THEN 1 ELSE 0 END)::NUMERIC / COUNT(*) * 100,
        2
    ) as profit_rate
FROM predictions p
JOIN learning_history lh ON p.prediction_id = lh.prediction_id
WHERE p.predicted_at >= CURRENT_DATE - INTERVAL '10 years'  -- ← 期間フィルター
  AND lh.actual_result IS NOT NULL;
```

---

## Pythonコード例

### **特徴量生成時**

```python
from datetime import datetime, timedelta
from src.config import ML_TRAINING_YEARS_BACK

def get_training_features(race_date=None):
    """
    訓練用特徴量を取得（直近N年分）

    Args:
        race_date: 基準日（省略時は今日）

    Returns:
        pd.DataFrame: 特徴量データ
    """
    if race_date is None:
        race_date = datetime.now().date()

    # 直近N年の開始日を計算
    cutoff_date = race_date - timedelta(days=365 * ML_TRAINING_YEARS_BACK)

    logger.info(f"訓練データ取得: {cutoff_date} 〜 {race_date} ({ML_TRAINING_YEARS_BACK}年分)")

    query = """
        SELECT *
        FROM race
        WHERE race_date >= %s
          AND race_date < %s
          AND finish_position IS NOT NULL
    """

    df = pd.read_sql(query, conn, params=(cutoff_date, race_date))
    logger.info(f"取得データ件数: {len(df)} レース")

    return df
```

### **馬の過去成績取得**

```python
from src.config import PREDICTION_REFERENCE_YEARS

def get_horse_history(horse_id, target_race_date, years_back=PREDICTION_REFERENCE_YEARS):
    """
    馬の過去成績を取得（直近N年分）

    Args:
        horse_id: 馬ID
        target_race_date: 予想対象レースの日付
        years_back: 何年前まで遡るか

    Returns:
        pd.DataFrame: 過去成績
    """
    cutoff_date = target_race_date - timedelta(days=365 * years_back)

    query = """
        SELECT
            race_date,
            race_name,
            finish_position,
            odds,
            prize_money
        FROM race
        WHERE horse_id = %s
          AND race_date >= %s
          AND race_date < %s
        ORDER BY race_date DESC
        LIMIT 20
    """

    df = pd.read_sql(query, conn, params=(horse_id, cutoff_date, target_race_date))
    return df
```

---

## パフォーマンス最適化

### **インデックス作成**

期間フィルタリングを高速化するため、`race_date`にインデックスを作成：

```sql
-- race_dateにインデックス作成
CREATE INDEX IF NOT EXISTS idx_race_date ON race(race_date);

-- 複合インデックス（よく使うカラムの組み合わせ）
CREATE INDEX IF NOT EXISTS idx_race_date_horse
ON race(race_date, horse_id);

CREATE INDEX IF NOT EXISTS idx_race_date_jockey
ON race(race_date, jockey_id);
```

### **パーティショニング（将来的）**

データ量が非常に大きくなった場合は、年単位でテーブルをパーティショニング：

```sql
-- PostgreSQL 10以降のパーティショニング例
CREATE TABLE race_partitioned (
    race_id VARCHAR PRIMARY KEY,
    race_date DATE NOT NULL,
    -- その他のカラム
) PARTITION BY RANGE (race_date);

-- 年ごとのパーティション作成
CREATE TABLE race_2024 PARTITION OF race_partitioned
FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');

CREATE TABLE race_2023 PARTITION OF race_partitioned
FOR VALUES FROM ('2023-01-01') TO ('2024-01-01');
-- ...
```

---

## データ量の見積もり

### **全期間（40年分）**
- レース数: 約120,000
- 出走馬: 約216万
- ストレージ: 30-50GB

### **使用データ（10年分）**
- レース数: 約30,000 (25%)
- 出走馬: 約54万 (25%)
- **クエリ速度: 全期間の4倍高速**

---

## メンテナンス

### **古いデータのアーカイブ（オプション）**

将来的に、10年以上前のデータをアーカイブテーブルに移動：

```sql
-- アーカイブテーブル作成
CREATE TABLE race_archive AS
SELECT * FROM race
WHERE race_date < CURRENT_DATE - INTERVAL '10 years';

-- 本テーブルから古いデータ削除（慎重に！）
-- DELETE FROM race
-- WHERE race_date < CURRENT_DATE - INTERVAL '10 years';
```

**注意**: アーカイブは慎重に。一度削除すると復元が困難。

---

## まとめ

- ✅ データベースには**全期間保存**（将来の分析用）
- ✅ 機械学習には**直近10年分のみ使用**（精度と速度のバランス）
- ✅ `config.py`で期間を一元管理
- ✅ SQLクエリに `WHERE race_date >= CURRENT_DATE - INTERVAL 'N years'` を追加
- ✅ インデックス作成でパフォーマンス最適化

この設計により、柔軟性とパフォーマンスを両立できます！
