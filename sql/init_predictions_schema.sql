-- ============================================
-- 予想システム用DB初期化スクリプト
-- ============================================
-- 目標: 回収率200%達成のためのデータ基盤構築
--
-- 使用方法:
--   psql -U postgres -d keiba_db -f sql/init_predictions_schema.sql

-- スキーマ作成
-- ============================================

CREATE SCHEMA IF NOT EXISTS predictions;

COMMENT ON SCHEMA predictions IS '競馬予想システム用スキーマ';


-- テーブル作成
-- ============================================

-- 4.1 predictions テーブル（予想内容）
-- ============================================

CREATE TABLE IF NOT EXISTS predictions.predictions (
    id SERIAL PRIMARY KEY,
    race_id VARCHAR(20) NOT NULL,       -- レースID（JRA-VAN形式）
    race_name VARCHAR(100) NOT NULL,    -- レース名
    race_date DATE NOT NULL,            -- レース日
    venue VARCHAR(50),                  -- 競馬場

    -- 予想内容（JSON）
    analysis_result JSONB,              -- フェーズ1: 分析結果
    prediction_result JSONB,            -- フェーズ2: 予想結果

    -- 投資・期待値
    total_investment INTEGER,           -- 総投資額（円）
    expected_return INTEGER,            -- 期待回収額（円）
    expected_roi NUMERIC(5,2),          -- 期待ROI

    -- 実行情報
    llm_model VARCHAR(50),              -- 使用LLMモデル
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_race_id UNIQUE(race_id)
);

COMMENT ON TABLE predictions.predictions IS '予想内容を保存するテーブル';
COMMENT ON COLUMN predictions.predictions.analysis_result IS 'フェーズ1の分析結果（JSON形式）';
COMMENT ON COLUMN predictions.predictions.prediction_result IS 'フェーズ2の予想結果（JSON形式）';

-- インデックス作成
CREATE INDEX IF NOT EXISTS idx_predictions_race_date ON predictions.predictions(race_date);
CREATE INDEX IF NOT EXISTS idx_predictions_venue ON predictions.predictions(venue);
CREATE INDEX IF NOT EXISTS idx_predictions_created_at ON predictions.predictions(created_at);


-- 4.2 results テーブル（実績・結果）
-- ============================================

CREATE TABLE IF NOT EXISTS predictions.results (
    id SERIAL PRIMARY KEY,
    prediction_id INTEGER NOT NULL,     -- predictionsテーブルの外部キー

    -- 実際の結果
    actual_result JSONB,                -- 実際のレース結果（JSON）

    -- 収支
    total_return INTEGER,               -- 実際の回収額（円）
    profit INTEGER,                     -- 収支（円）
    actual_roi NUMERIC(5,2),            -- 実際のROI

    -- 精度
    prediction_accuracy NUMERIC(3,2),   -- 予想精度（0.00-1.00）

    -- 反省内容
    reflection_result JSONB,            -- フェーズ3: 反省結果（JSON）

    -- 更新日時
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_prediction FOREIGN KEY (prediction_id)
        REFERENCES predictions.predictions(id) ON DELETE CASCADE
);

COMMENT ON TABLE predictions.results IS 'レース結果と収支を保存するテーブル';
COMMENT ON COLUMN predictions.results.actual_result IS '実際のレース結果（JSON形式）';
COMMENT ON COLUMN predictions.results.reflection_result IS 'フェーズ3の反省結果（JSON形式）';

-- インデックス作成
CREATE INDEX IF NOT EXISTS idx_results_prediction_id ON predictions.results(prediction_id);
CREATE INDEX IF NOT EXISTS idx_results_updated_at ON predictions.results(updated_at);


-- 4.3 stats テーブル（統計情報）
-- ============================================

CREATE TABLE IF NOT EXISTS predictions.stats (
    id SERIAL PRIMARY KEY,
    period VARCHAR(20) NOT NULL,        -- 集計期間（daily/weekly/monthly/all）
    start_date DATE,
    end_date DATE,

    -- 基本統計
    total_races INTEGER DEFAULT 0,      -- 予想レース数
    total_investment INTEGER DEFAULT 0, -- 総投資額
    total_return INTEGER DEFAULT 0,     -- 総回収額
    total_profit INTEGER DEFAULT 0,     -- 総収支
    roi NUMERIC(5,2),                   -- 回収率（％）

    -- 的中率
    hit_count INTEGER DEFAULT 0,        -- 的中数
    hit_rate NUMERIC(3,2),              -- 的中率（0.00-1.00）

    -- その他
    best_roi NUMERIC(5,2),              -- 最高ROI
    worst_roi NUMERIC(5,2),             -- 最低ROI

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_period UNIQUE(period, start_date, end_date)
);

COMMENT ON TABLE predictions.stats IS '統計情報を保存するテーブル';
COMMENT ON COLUMN predictions.stats.period IS '集計期間（daily/weekly/monthly/all）';
COMMENT ON COLUMN predictions.stats.roi IS '回収率（目標200%）';

-- インデックス作成
CREATE INDEX IF NOT EXISTS idx_stats_period ON predictions.stats(period);
CREATE INDEX IF NOT EXISTS idx_stats_date_range ON predictions.stats(start_date, end_date);


-- ビュー作成（便利クエリ）
-- ============================================

-- 最近の予想と結果を結合したビュー
CREATE OR REPLACE VIEW predictions.recent_predictions_with_results AS
SELECT
    p.id,
    p.race_id,
    p.race_name,
    p.race_date,
    p.venue,
    p.total_investment,
    p.expected_return,
    p.expected_roi,
    r.total_return AS actual_return,
    r.actual_roi,
    r.profit,
    r.prediction_accuracy,
    p.llm_model,
    p.created_at,
    r.updated_at AS result_updated_at
FROM predictions.predictions p
LEFT JOIN predictions.results r ON p.id = r.prediction_id
ORDER BY p.created_at DESC
LIMIT 100;

COMMENT ON VIEW predictions.recent_predictions_with_results IS '最近100件の予想と結果を結合したビュー';


-- 完了メッセージ
-- ============================================

DO $$
BEGIN
    RAISE NOTICE '============================================';
    RAISE NOTICE '予想システム用DBの初期化が完了しました！';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'スキーマ: predictions';
    RAISE NOTICE 'テーブル:';
    RAISE NOTICE '  - predictions.predictions (予想内容)';
    RAISE NOTICE '  - predictions.results (実績・結果)';
    RAISE NOTICE '  - predictions.stats (統計情報)';
    RAISE NOTICE 'ビュー:';
    RAISE NOTICE '  - predictions.recent_predictions_with_results';
    RAISE NOTICE '============================================';
END $$;
