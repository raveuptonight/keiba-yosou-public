-- データベースインデックス最適化スクリプト（実テーブル名対応）
-- PostgreSQL用パフォーマンス改善

-- ===== pg_trgm拡張を有効化（LIKE検索の高速化）=====
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ===== race_shosai（レース詳細）テーブル =====

-- レース名の部分一致検索用（GINインデックス）
CREATE INDEX IF NOT EXISTS idx_race_shosai_name_trgm
ON race_shosai USING gin (kyosomei_hondai gin_trgm_ops);

-- 開催日検索用（複合インデックス）
CREATE INDEX IF NOT EXISTS idx_race_shosai_date
ON race_shosai (kaisai_nen, kaisai_gappi);

-- 競馬場・グレード検索用
CREATE INDEX IF NOT EXISTS idx_race_shosai_jyocd_grade
ON race_shosai (keibajo_code, grade_code)
WHERE data_kubun = '7';

-- データ区分フィルタ用
CREATE INDEX IF NOT EXISTS idx_race_shosai_data_kubun
ON race_shosai (data_kubun);

-- レース番号検索用
CREATE INDEX IF NOT EXISTS idx_race_shosai_race_bango
ON race_shosai (race_bango);


-- ===== umagoto_race_joho（馬毎レース情報）テーブル =====

-- 血統登録番号検索用（馬の過去成績）
CREATE INDEX IF NOT EXISTS idx_umagoto_race_kettonum
ON umagoto_race_joho (ketto_toroku_bango);

-- レースID検索用（出走馬一覧）
CREATE INDEX IF NOT EXISTS idx_umagoto_race_raceid
ON umagoto_race_joho (race_code);

-- 騎手成績検索用
CREATE INDEX IF NOT EXISTS idx_umagoto_race_kishucode
ON umagoto_race_joho (kishu_code);

-- 調教師成績検索用
CREATE INDEX IF NOT EXISTS idx_umagoto_race_chokyosicode
ON umagoto_race_joho (chokyoshi_code);

-- 複合インデックス: 馬の過去成績取得用
CREATE INDEX IF NOT EXISTS idx_umagoto_race_kettonum_kubun
ON umagoto_race_joho (ketto_toroku_bango, data_kubun)
INCLUDE (race_code, kakutei_chakujun, soha_time);

-- 複合インデックス: レース出走馬取得用
CREATE INDEX IF NOT EXISTS idx_umagoto_race_raceid_kubun
ON umagoto_race_joho (race_code, data_kubun)
INCLUDE (ketto_toroku_bango, umaban, kishu_code, chokyoshi_code);


-- ===== kyosoba_master2（競走馬マスタ）テーブル =====

-- 血統登録番号検索用（既に主キーだが明示）
CREATE INDEX IF NOT EXISTS idx_kyosoba_master2_kettonum
ON kyosoba_master2 (ketto_toroku_bango);

-- 馬名検索用
CREATE INDEX IF NOT EXISTS idx_kyosoba_master2_bamei_trgm
ON kyosoba_master2 USING gin (bamei gin_trgm_ops);

-- 調教師検索用
CREATE INDEX IF NOT EXISTS idx_kyosoba_master2_chokyosicode
ON kyosoba_master2 (chokyoshi_code);


-- ===== kishu_master（騎手マスタ）テーブル =====

-- 騎手コード検索用
CREATE INDEX IF NOT EXISTS idx_kishu_master_code
ON kishu_master (kishu_code);

-- 騎手名検索用
CREATE INDEX IF NOT EXISTS idx_kishu_master_name_trgm
ON kishu_master USING gin (kishumei gin_trgm_ops);


-- ===== chokyoshi_master（調教師マスタ）テーブル =====

-- 調教師コード検索用
CREATE INDEX IF NOT EXISTS idx_chokyoshi_master_code
ON chokyoshi_master (chokyoshi_code);

-- 調教師名検索用
CREATE INDEX IF NOT EXISTS idx_chokyoshi_master_name_trgm
ON chokyoshi_master USING gin (chokyoshimei gin_trgm_ops);


-- ===== odds1_tansho（単勝オッズ）テーブル =====

-- レースIDとデータ区分での検索用
CREATE INDEX IF NOT EXISTS idx_odds1_tansho_raceid_kubun
ON odds1_tansho (race_code, data_kubun);


-- ===== 統計情報の更新 =====
ANALYZE race_shosai;
ANALYZE umagoto_race_joho;
ANALYZE kyosoba_master2;
ANALYZE kishu_master;
ANALYZE chokyoshi_master;
ANALYZE odds1_tansho;

-- インデックス作成完了
SELECT 'Database indexes optimized successfully!' as status;
