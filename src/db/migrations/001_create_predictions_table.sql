-- ===========================================
-- マイグレーション: 予想・分析結果テーブル作成
-- ===========================================
-- 作成日: 2026-01-06
-- 説明: レース予想結果と分析結果を保存するテーブル

-- predictions テーブル作成（レース毎の予想結果）
CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    race_code TEXT NOT NULL,
    race_date DATE NOT NULL,
    keibajo TEXT NOT NULL,
    race_number TEXT NOT NULL,
    kyori INTEGER,

    -- 予想結果（JSONB形式で保存）
    -- 各馬: umaban, bamei, pred_score, win_prob, place_prob, pred_rank
    prediction_data JSONB NOT NULL,

    -- メタデータ
    model_version TEXT,
    predicted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- ユニーク制約（同一レースに対する予想は1つ）
    CONSTRAINT uq_predictions_race UNIQUE (race_code)
);

-- インデックス作成
CREATE INDEX IF NOT EXISTS idx_predictions_race_date ON predictions (race_date DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_keibajo ON predictions (keibajo);
CREATE INDEX IF NOT EXISTS idx_predictions_predicted_at ON predictions (predicted_at DESC);

-- analysis_results テーブル作成（日別の分析結果）
CREATE TABLE IF NOT EXISTS analysis_results (
    id SERIAL PRIMARY KEY,
    analysis_date DATE NOT NULL,

    -- 統計情報
    total_races INTEGER NOT NULL DEFAULT 0,
    analyzed_races INTEGER NOT NULL DEFAULT 0,

    -- 的中数
    tansho_hit INTEGER NOT NULL DEFAULT 0,
    fukusho_hit INTEGER NOT NULL DEFAULT 0,
    umaren_hit INTEGER NOT NULL DEFAULT 0,
    sanrenpuku_hit INTEGER NOT NULL DEFAULT 0,
    top3_cover INTEGER NOT NULL DEFAULT 0,

    -- 的中率
    tansho_rate FLOAT,
    fukusho_rate FLOAT,
    umaren_rate FLOAT,
    sanrenpuku_rate FLOAT,
    top3_cover_rate FLOAT,
    mrr FLOAT,

    -- 詳細データ（JSONB）
    -- by_venue, by_distance, by_track, calibration, misses
    detail_data JSONB,

    -- メタデータ
    analyzed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- ユニーク制約（同一日の分析は1つ）
    CONSTRAINT uq_analysis_date UNIQUE (analysis_date)
);

-- インデックス作成
CREATE INDEX IF NOT EXISTS idx_analysis_date ON analysis_results (analysis_date DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_analyzed_at ON analysis_results (analyzed_at DESC);

-- accuracy_tracking テーブル作成（累積精度トラッキング）
CREATE TABLE IF NOT EXISTS accuracy_tracking (
    id SERIAL PRIMARY KEY,

    -- 累積統計
    total_races INTEGER NOT NULL DEFAULT 0,
    total_tansho_hit INTEGER NOT NULL DEFAULT 0,
    total_fukusho_hit INTEGER NOT NULL DEFAULT 0,
    total_umaren_hit INTEGER NOT NULL DEFAULT 0,
    total_sanrenpuku_hit INTEGER NOT NULL DEFAULT 0,

    -- 累積的中率
    cumulative_tansho_rate FLOAT,
    cumulative_fukusho_rate FLOAT,
    cumulative_umaren_rate FLOAT,
    cumulative_sanrenpuku_rate FLOAT,

    -- 更新情報
    last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 初期レコード挿入（1レコードのみ）
INSERT INTO accuracy_tracking (total_races) VALUES (0) ON CONFLICT DO NOTHING;

-- コメント追加
COMMENT ON TABLE predictions IS 'レース毎の予想結果';
COMMENT ON TABLE analysis_results IS '日別の予想精度分析結果';
COMMENT ON TABLE accuracy_tracking IS '累積精度トラッキング';
