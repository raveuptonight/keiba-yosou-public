# インデックス設計

## 概要

予想システムで高速なデータ取得を実現するためのインデックス設計。
JRA-VAN 27種類のテーブルに対する最適なインデックス戦略を定義します。

---

## インデックス設計の方針

### 基本方針

1. **主キーは自動的にインデックス作成される**（B-tree）
2. **外部キーにはインデックスを作成**（JOIN高速化）
3. **WHERE句で頻繁に使うカラムにインデックス**
4. **複合インデックスは選択性の高いカラムから並べる**
5. **部分インデックスで不要なデータを除外**
6. **10年分のデータ利用を前提**（ML_TRAINING_YEARS_BACK=10）

### パフォーマンス目標

- レース1件の出走馬全データ取得: **< 100ms**
- 特定馬の過去10レース取得: **< 50ms**
- 調教データ取得（直近1ヶ月）: **< 30ms**
- オッズデータ取得: **< 20ms**

---

## テーブル別インデックス設計

### 1. RA（レース詳細）

**主キー**: `race_id` (16桁) ※自動インデックス

**追加インデックス**:

```sql
-- 開催日での検索（今日・明日のレース取得）
CREATE INDEX idx_ra_kaisai_date
ON race (kaisai_year, kaisai_monthday);

-- 競馬場での検索
CREATE INDEX idx_ra_jyocd
ON race (jyocd, kaisai_year, kaisai_monthday);

-- グレード別検索（G1レースのみ取得等）
CREATE INDEX idx_ra_grade
ON race (grade_cd, kaisai_year)
WHERE grade_cd IN ('A', 'B', 'C');  -- 部分インデックス（重賞のみ）

-- 距離・トラック別検索
CREATE INDEX idx_ra_course
ON race (jyocd, track_cd, kyori);

-- データ区分での絞り込み（確定データのみ）
CREATE INDEX idx_ra_data_kubun
ON race (data_kubun, kaisai_year, kaisai_monthday)
WHERE data_kubun IN ('7', 'A');  -- 確定成績のみ
```

**想定クエリ**:
```sql
-- 今日のレース一覧
SELECT * FROM race
WHERE kaisai_year = '2024'
  AND kaisai_monthday = '1228'
  AND data_kubun = '7';  -- 確定データ
-- → idx_ra_kaisai_date + idx_ra_data_kubun

-- 東京芝1600mのレコード取得
SELECT * FROM race
WHERE jyocd = '05'
  AND track_cd = '1'
  AND kyori = 1600;
-- → idx_ra_course
```

---

### 2. SE（馬毎レース情報）

**主キー**: `race_id + umaban` (18桁) ※自動インデックス

**追加インデックス**:

```sql
-- 外部キー: race_id（JOIN用）
CREATE INDEX idx_se_race_id
ON uma_race (race_id);

-- 外部キー: kettonum（馬の過去成績取得）
CREATE INDEX idx_se_kettonum
ON uma_race (kettonum, kaisai_year DESC, kaisai_monthday DESC);

-- 騎手の過去成績
CREATE INDEX idx_se_kishu
ON uma_race (kishu_cd, kaisai_year DESC);

-- 調教師の過去成績
CREATE INDEX idx_se_chokyoshi
ON uma_race (chokyoshi_cd, kaisai_year DESC);

-- 確定データのみ（data_kubun = 7）
CREATE INDEX idx_se_data_kubun
ON uma_race (data_kubun, kaisai_year)
WHERE data_kubun = '7';  -- 確定成績のみ

-- 着順での絞り込み（勝利レースのみ等）
CREATE INDEX idx_se_chakujun
ON uma_race (kettonum, kakutei_chakujun, kaisai_year DESC)
WHERE kakutei_chakujun <= 3;  -- 3着以内のみ
```

**想定クエリ**:
```sql
-- 特定馬の過去10レース取得
SELECT * FROM uma_race
WHERE kettonum = '2020100001'
  AND data_kubun = '7'
ORDER BY kaisai_year DESC, kaisai_monthday DESC
LIMIT 10;
-- → idx_se_kettonum

-- レースの出走馬一覧
SELECT * FROM uma_race
WHERE race_id = '202412280506'
ORDER BY umaban;
-- → 主キー（race_id + umaban）
```

---

### 3. UM（競走馬マスタ）

**主キー**: `kettonum` (10桁) ※自動インデックス

**追加インデックス**:

```sql
-- 馬名での検索（あいまい検索用）
CREATE INDEX idx_um_bamei
ON uma (bamei);

-- 生年月日での検索（同世代の馬検索）
CREATE INDEX idx_um_birth_year
ON uma (SUBSTRING(birth_date, 1, 4));  -- 生年のみ

-- 収得賞金での検索（クラス分け）
CREATE INDEX idx_um_shutoku
ON uma (heichi_shutoku DESC);  -- 降順（高額順）

-- 性別・馬齢での絞り込み
CREATE INDEX idx_um_sex_age
ON uma (sex_cd, barei);
```

---

### 4. KS（騎手マスタ）、CH（調教師マスタ）

**主キー**: `kishu_cd` / `chokyoshi_cd` (5桁) ※自動インデックス

**追加インデックス**:

```sql
-- 騎手名での検索
CREATE INDEX idx_ks_mei
ON kishu (kishu_mei);

-- 所属での検索
CREATE INDEX idx_ks_shozoku
ON kishu (shozoku);

-- 現役騎手のみ
CREATE INDEX idx_ks_massho
ON kishu (massho_kubun)
WHERE massho_kubun = '0';  -- 現役のみ

-- 調教師も同様
CREATE INDEX idx_ch_mei ON chokyoshi (chokyoshi_mei);
CREATE INDEX idx_ch_shozoku ON chokyoshi (shozoku);
CREATE INDEX idx_ch_massho ON chokyoshi (massho_kubun) WHERE massho_kubun = '0';
```

---

### 5. HN（繁殖馬マスタ）、SK（産駒マスタ）

**主キー**: `hansyoku_num` / `kettonum` ※自動インデックス

**追加インデックス**:

```sql
-- HN: 父馬での検索（父の産駒一覧）
CREATE INDEX idx_hn_chichi
ON hansyoku (chichi_hansyoku_num);

-- HN: 母馬での検索（母の産駒一覧）
CREATE INDEX idx_hn_haha
ON hansyoku (haha_hansyoku_num);

-- HN: 血統登録番号での検索
CREATE INDEX idx_hn_kettonum
ON hansyoku (kettonum);

-- SK: 3代血統の各要素（配列インデックス）
-- ※PostgreSQLの場合、GINインデックスで配列全体を検索可能
CREATE INDEX idx_sk_sandai_ketto
ON sanku USING GIN (sandai_ketto);

-- SK: 父（sandai_ketto[0]）での検索
CREATE INDEX idx_sk_chichi
ON sanku ((sandai_ketto[1]));  -- 配列は1始まり

-- SK: 母父（sandai_ketto[4]）での検索
CREATE INDEX idx_sk_bohha
ON sanku ((sandai_ketto[5]));  -- 母父
```

**想定クエリ**:
```sql
-- ディープインパクト産駒の検索
SELECT sk.*
FROM sanku sk
WHERE sandai_ketto[1] = '2002100001';  -- ディープインパクトの繁殖登録番号
-- → idx_sk_chichi

-- 母父サンデーサイレンスの馬
SELECT sk.*
FROM sanku sk
WHERE sandai_ketto[5] = '1986100001';  -- サンデーサイレンスの繁殖登録番号
-- → idx_sk_bohha
```

---

### 6. BT（系統情報）

**主キー**: `hansyoku_num` ※自動インデックス

**追加インデックス**:

```sql
-- 系統名での検索
CREATE INDEX idx_bt_keitou_mei
ON keitou (keitou_mei);

-- 系統ID（階層検索）
CREATE INDEX idx_bt_keitou_id
ON keitou (keitou_id);

-- 全文検索用（系統説明の検索）
CREATE INDEX idx_bt_keitou_setumei_fts
ON keitou USING GIN (to_tsvector('japanese', keitou_setumei));
```

---

### 7. HC（坂路調教）、WC（ウッドチップ調教）

**主キー**: `chokyo_date + kettonum` ※自動インデックス

**追加インデックス**:

```sql
-- HC: 馬ごとの最新調教取得
CREATE INDEX idx_hc_kettonum_date
ON hanro_chokyo (kettonum, chokyo_date DESC);

-- HC: 調教日での検索
CREATE INDEX idx_hc_date
ON hanro_chokyo (chokyo_date, tresen_kubun);

-- HC: 4ハロンタイムでのソート（優秀な調教馬検索）
CREATE INDEX idx_hc_time_4f
ON hanro_chokyo (time_4f)
WHERE time_4f > 0;  -- 測定不良を除外

-- WC: 同様のインデックス
CREATE INDEX idx_wc_kettonum_date ON wood_chokyo (kettonum, chokyo_date DESC);
CREATE INDEX idx_wc_date ON wood_chokyo (chokyo_date, tresen_kubun);
CREATE INDEX idx_wc_time_6f ON wood_chokyo (time_6f) WHERE time_6f > 0;
```

**想定クエリ**:
```sql
-- 特定馬の直近1ヶ月の調教データ
SELECT * FROM hanro_chokyo
WHERE kettonum = '2020100001'
  AND chokyo_date >= '20241128'
  AND chokyo_date <= '20241228'
ORDER BY chokyo_date DESC;
-- → idx_hc_kettonum_date
```

---

### 8. CK（出走別着度数）

**主キー**: `race_id + kettonum` (26桁) ※自動インデックス

**追加インデックス**:

```sql
-- 外部キー: race_id
CREATE INDEX idx_ck_race_id
ON chakudo (race_id);

-- 外部キー: kettonum
CREATE INDEX idx_ck_kettonum
ON chakudo (kettonum, kaisai_year DESC);

-- 騎手コード
CREATE INDEX idx_ck_kishu
ON chakudo (kishu_cd);

-- 調教師コード
CREATE INDEX idx_ck_chokyoshi
ON chakudo (chokyoshi_cd);
```

**想定クエリ**:
```sql
-- レースの出走馬の着度数データ取得
SELECT * FROM chakudo
WHERE race_id = '202412280506';
-- → idx_ck_race_id

-- 特定馬の最新の着度数データ
SELECT * FROM chakudo
WHERE kettonum = '2020100001'
ORDER BY kaisai_year DESC, kaisai_monthday DESC
LIMIT 1;
-- → idx_ck_kettonum
```

---

### 9. HR（払戻）

**主キー**: `race_id` ※自動インデックス

**追加インデックス**:

```sql
-- データ区分での絞り込み（確定データのみ）
CREATE INDEX idx_hr_data_kubun
ON haraimodoshi (data_kubun, kaisai_year)
WHERE data_kubun IN ('4', '5');  -- 確定払戻のみ

-- 開催日での検索
CREATE INDEX idx_hr_kaisai_date
ON haraimodoshi (kaisai_year, kaisai_monthday);
```

---

### 10. O1～O6（オッズ）

**主キー**: `race_id` (+ `happyo_jifun` ※中間オッズのみ) ※自動インデックス

**追加インデックス**:

```sql
-- データ区分での絞り込み（最終オッズのみ）
CREATE INDEX idx_o1_data_kubun
ON odds_tanpuku (race_id, data_kubun)
WHERE data_kubun = '3';  -- 最終オッズのみ

-- 同様に O2～O6 も
CREATE INDEX idx_o2_data_kubun ON odds_umaren (race_id, data_kubun) WHERE data_kubun = '3';
CREATE INDEX idx_o3_data_kubun ON odds_wide (race_id, data_kubun) WHERE data_kubun = '3';
CREATE INDEX idx_o4_data_kubun ON odds_umatan (race_id, data_kubun) WHERE data_kubun = '3';
CREATE INDEX idx_o5_data_kubun ON odds_sanrenpuku (race_id, data_kubun) WHERE data_kubun = '3';
CREATE INDEX idx_o6_data_kubun ON odds_sanrentan (race_id, data_kubun) WHERE data_kubun = '3';
```

---

### 11. TK（特別登録馬）

**主キー**: `race_id + kettonum` ※自動インデックス

**追加インデックス**:

```sql
-- 開催日での検索（今後のレース一覧）
CREATE INDEX idx_tk_kaisai_date
ON tokubetsu_toroku (kaisai_year, kaisai_monthday, jyocd);

-- 競馬場での検索
CREATE INDEX idx_tk_jyocd
ON tokubetsu_toroku (jyocd, kaisai_year, kaisai_monthday);

-- グレード別（重賞のみ）
CREATE INDEX idx_tk_grade
ON tokubetsu_toroku (grade_cd, kaisai_year)
WHERE grade_cd IN ('A', 'B', 'C');
```

**想定クエリ**:
```sql
-- 明日のレース一覧
SELECT DISTINCT race_id, kyoso_hondai, grade_cd
FROM tokubetsu_toroku
WHERE kaisai_year = '2024'
  AND kaisai_monthday = '1229';
-- → idx_tk_kaisai_date
```

---

### 12. YS（開催スケジュール）

**主キー**: `kaisai_date + jyocd + kaisai_kai + kaisai_nichime` ※自動インデックス

**追加インデックス**:

```sql
-- 開催日での検索
CREATE INDEX idx_ys_kaisai_date
ON kaisai_schedule (kaisai_year, kaisai_monthday);

-- 競馬場での検索
CREATE INDEX idx_ys_jyocd
ON kaisai_schedule (jyocd, kaisai_year);

-- データ区分（開催直前のみ）
CREATE INDEX idx_ys_data_kubun
ON kaisai_schedule (data_kubun)
WHERE data_kubun IN ('2', '3');  -- 開催直前・終了
```

---

### 13. CS（コース情報）

**主キー**: `jyocd + kyori + track_cd + kaishu_ymd` ※自動インデックス

**追加インデックス**:

```sql
-- 競馬場・距離・トラックでの検索
CREATE INDEX idx_cs_course
ON course_info (jyocd, track_cd, kyori, kaishu_ymd DESC);

-- 全文検索用（コース説明）
CREATE INDEX idx_cs_setumei_fts
ON course_info USING GIN (to_tsvector('japanese', course_setumei));
```

**想定クエリ**:
```sql
-- 東京芝1600mの最新コース情報
SELECT * FROM course_info
WHERE jyocd = '05'
  AND track_cd = '1'
  AND kyori = 1600
  AND kaishu_ymd <= '20241228'
ORDER BY kaishu_ymd DESC
LIMIT 1;
-- → idx_cs_course
```

---

### 14. RC（レコードマスタ）

**主キー**: `record_shikibetsu + jyocd + kyoso_shubetsu + kyori + track_cd` ※自動インデックス

**追加インデックス**:

```sql
-- コースレコード検索
CREATE INDEX idx_rc_course_record
ON record_master (jyocd, track_cd, kyori, record_kubun)
WHERE record_shikibetsu = '1' AND record_kubun = '2';  -- コースレコードのレコードタイム

-- G1レコード検索
CREATE INDEX idx_rc_g1_record
ON record_master (tokubetsu_kyoso_num, record_kubun)
WHERE record_shikibetsu = '2' AND record_kubun = '2';  -- G1レコードのレコードタイム
```

---

### 15. WE（天候馬場状態）

**主キー**: `race_date + jyocd + kaisai_kai + kaisai_nichime + happyo_jifun + henkou_shikibetsu` ※自動インデックス

**追加インデックス**:

```sql
-- 開催日・競馬場での最新状態取得
CREATE INDEX idx_we_latest
ON tenkou_baba (kaisai_year, kaisai_monthday, jyocd, happyo_tsukihi_jifun DESC);

-- 変更識別での絞り込み
CREATE INDEX idx_we_henkou
ON tenkou_baba (henkou_shikibetsu, kaisai_year);
```

**想定クエリ**:
```sql
-- 東京競馬場の今日の最新馬場状態
SELECT * FROM tenkou_baba
WHERE kaisai_year = '2024'
  AND kaisai_monthday = '1228'
  AND jyocd = '05'
ORDER BY happyo_tsukihi_jifun DESC
LIMIT 1;
-- → idx_we_latest
```

---

### 16. AV（出走取消）、JC（騎手変更）、TC（発走時刻変更）、CC（コース変更）

**主キー**: 各テーブルごとに異なる ※自動インデックス

**追加インデックス**:

```sql
-- AV: race_idでの検索
CREATE INDEX idx_av_race_id ON torikeshi (race_id);

-- JC: race_idでの検索
CREATE INDEX idx_jc_race_id ON kishu_henkou (race_id);

-- TC: race_idでの検索
CREATE INDEX idx_tc_race_id ON jikoku_henkou (race_id);

-- CC: race_idでの検索
CREATE INDEX idx_cc_race_id ON course_henkou (race_id);
```

---

## インデックスメンテナンス

### 定期的なメンテナンス

```sql
-- インデックスの再構築（月次）
REINDEX DATABASE keiba_db;

-- VACUUM ANALYZE（週次）
VACUUM ANALYZE;

-- 統計情報の更新（日次）
ANALYZE;
```

### インデックスサイズのモニタリング

```sql
-- インデックスサイズの確認
SELECT
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC
LIMIT 20;

-- 未使用インデックスの検出
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE idx_scan = 0
  AND schemaname = 'public'
ORDER BY pg_relation_size(indexrelid) DESC;
```

---

## パフォーマンスチューニング

### クエリ実行計画の確認

```sql
-- EXPLAIN ANALYZE で実行計画を確認
EXPLAIN ANALYZE
SELECT * FROM uma_race
WHERE kettonum = '2020100001'
  AND data_kubun = '7'
ORDER BY kaisai_year DESC, kaisai_monthday DESC
LIMIT 10;

-- インデックスが使われているか確認
-- → Index Scan using idx_se_kettonum が出ればOK
-- → Seq Scan が出たらインデックスが使われていない
```

### PostgreSQL設定の最適化

```sql
-- shared_buffers: メモリの25%程度
-- effective_cache_size: メモリの50-75%
-- work_mem: 並列処理用メモリ
-- maintenance_work_mem: インデックス作成用メモリ

-- 設定例（16GBメモリの場合）
ALTER SYSTEM SET shared_buffers = '4GB';
ALTER SYSTEM SET effective_cache_size = '12GB';
ALTER SYSTEM SET work_mem = '64MB';
ALTER SYSTEM SET maintenance_work_mem = '1GB';
ALTER SYSTEM SET random_page_cost = 1.1;  -- SSDの場合
```

---

## 次のステップ

1. ✅ **ER図作成完了** (docs/ER_DIAGRAM.md)
2. ✅ **インデックス設計完了** (docs/INDEX_DESIGN.md)
3. 次: **API設計** (docs/API_DESIGN.md)

データダウンロード完了後、上記のインデックスを順次作成してパフォーマンスを検証します。
