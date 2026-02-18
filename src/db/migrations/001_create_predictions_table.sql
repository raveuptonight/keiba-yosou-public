-- ===========================================
-- マイグレーション: 予想・分析結果テーブル作成
-- ===========================================
-- 更新日: 2026-01-06
-- 説明: レース予想・分析・バイアス結果を保存するテーブル

-- predictions テーブル（レース毎の予想結果）
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id TEXT PRIMARY KEY,
    race_id TEXT NOT NULL,
    race_date DATE NOT NULL,
    is_final BOOLEAN NOT NULL DEFAULT FALSE,
    prediction_result JSONB NOT NULL,
    predicted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_predictions_race_final UNIQUE (race_id, is_final)
);

CREATE INDEX IF NOT EXISTS idx_predictions_race_id ON predictions (race_id);
CREATE INDEX IF NOT EXISTS idx_predictions_race_date ON predictions (race_date DESC);

-- analysis_results テーブル（日別の予想精度分析結果）
CREATE TABLE IF NOT EXISTS analysis_results (
    id SERIAL PRIMARY KEY,
    analysis_date DATE NOT NULL,
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

    -- 回収率
    tansho_roi FLOAT,
    fukusho_roi FLOAT,
    axis_fukusho_roi FLOAT,
    tansho_investment INTEGER DEFAULT 0,
    tansho_return INTEGER DEFAULT 0,
    fukusho_investment INTEGER DEFAULT 0,
    fukusho_return INTEGER DEFAULT 0,

    -- 詳細データ（JSONB）
    detail_data JSONB,

    -- メタデータ
    analyzed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_analysis_date UNIQUE (analysis_date)
);

CREATE INDEX IF NOT EXISTS idx_analysis_date ON analysis_results (analysis_date DESC);

-- accuracy_tracking テーブル（累積精度トラッキング）
CREATE TABLE IF NOT EXISTS accuracy_tracking (
    id SERIAL PRIMARY KEY,
    total_races INTEGER NOT NULL DEFAULT 0,
    total_tansho_hit INTEGER NOT NULL DEFAULT 0,
    total_fukusho_hit INTEGER NOT NULL DEFAULT 0,
    total_umaren_hit INTEGER NOT NULL DEFAULT 0,
    total_sanrenpuku_hit INTEGER NOT NULL DEFAULT 0,
    cumulative_tansho_rate FLOAT,
    cumulative_fukusho_rate FLOAT,
    cumulative_umaren_rate FLOAT,
    cumulative_sanrenpuku_rate FLOAT,
    last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- daily_bias テーブル（日次バイアス分析結果）
CREATE TABLE IF NOT EXISTS daily_bias (
    id SERIAL PRIMARY KEY,
    target_date DATE NOT NULL,
    analyzed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_races INTEGER NOT NULL DEFAULT 0,

    -- バイアスデータ（JSONB）
    venue_biases JSONB,
    jockey_performances JSONB,

    CONSTRAINT uq_daily_bias_date UNIQUE (target_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_bias_date ON daily_bias (target_date DESC);

-- model_calibration テーブル（モデルキャリブレーション設定）
CREATE TABLE IF NOT EXISTS model_calibration (
    id SERIAL PRIMARY KEY,
    model_version TEXT NOT NULL,
    calibration_data JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- コメント
COMMENT ON TABLE analysis_results IS '日別の予想精度分析結果';
COMMENT ON TABLE accuracy_tracking IS '累積精度トラッキング（1レコードのみ）';
COMMENT ON TABLE daily_bias IS '日次バイアス分析結果（枠順・脚質・騎手）';
COMMENT ON TABLE model_calibration IS 'モデルキャリブレーション設定';
