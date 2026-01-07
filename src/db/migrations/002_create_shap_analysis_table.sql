-- ===========================================
-- マイグレーション: SHAP分析テーブル作成
-- ===========================================
-- 更新日: 2026-01-07
-- 説明: SHAP特徴量分析結果を保存するテーブル

-- shap_analysis テーブル（週次SHAP分析結果）
CREATE TABLE IF NOT EXISTS shap_analysis (
    id SERIAL PRIMARY KEY,
    analysis_date DATE NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,

    -- 基本統計
    total_races INTEGER NOT NULL DEFAULT 0,
    hit_count INTEGER NOT NULL DEFAULT 0,       -- 単勝的中数
    place_count INTEGER NOT NULL DEFAULT 0,     -- 複勝圏（2-3着）数
    miss_count INTEGER NOT NULL DEFAULT 0,      -- 4着以下数
    hit_rate FLOAT,                             -- 単勝的中率
    place_rate FLOAT,                           -- 複勝率

    -- SHAP値集計（JSONB）
    hit_contributions JSONB,                    -- 的中時の特徴量寄与度（平均）
    miss_contributions JSONB,                   -- 外れ時の特徴量寄与度（平均）
    diff_contributions JSONB,                   -- 差分（的中 - 外れ）

    -- メタデータ
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_shap_analysis_date UNIQUE (analysis_date)
);

CREATE INDEX IF NOT EXISTS idx_shap_analysis_date ON shap_analysis (analysis_date DESC);

COMMENT ON TABLE shap_analysis IS '週次SHAP特徴量分析結果';
COMMENT ON COLUMN shap_analysis.hit_contributions IS '的中時の特徴量別SHAP値平均';
COMMENT ON COLUMN shap_analysis.miss_contributions IS '外れ時の特徴量別SHAP値平均';
COMMENT ON COLUMN shap_analysis.diff_contributions IS '的中と外れの差分（正=的中時に高い）';
