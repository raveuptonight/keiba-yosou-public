-- 予想結果・学習履歴テーブル
-- PostgreSQLマイグレーション

-- 予想結果テーブル
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id SERIAL PRIMARY KEY,
    race_id VARCHAR(20) NOT NULL,
    race_date DATE NOT NULL,
    predicted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Phase 0: ML予測
    ml_scores JSONB NOT NULL,  -- ML予測結果（各馬のスコア）

    -- Phase 1: データ分析
    analysis JSONB NOT NULL,  -- LLMによるデータ分析結果

    -- Phase 2: 最終予想
    prediction JSONB NOT NULL,  -- 最終予想結果

    -- メタデータ
    model_version VARCHAR(50),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 学習履歴テーブル
CREATE TABLE IF NOT EXISTS learning_history (
    learning_id SERIAL PRIMARY KEY,
    prediction_id INTEGER REFERENCES predictions(prediction_id),
    race_id VARCHAR(20) NOT NULL,
    analyzed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- 実際の結果
    actual_result JSONB NOT NULL,  -- レース結果（着順など）

    -- ML分析
    ml_outlier_analysis JSONB NOT NULL,  -- ML外れ値分析結果
    ml_retrain_result JSONB,  -- 再学習結果

    -- LLM分析
    llm_failure_analysis JSONB NOT NULL,  -- LLM失敗分析結果

    -- 学習ポイント（抽出済み）
    learning_points TEXT[],  -- 今後の予想で参照する学習ポイント

    -- 精度指標
    accuracy_metrics JSONB,  -- 的中率、誤差など

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- インデックス
CREATE INDEX IF NOT EXISTS idx_predictions_race_id ON predictions(race_id);
CREATE INDEX IF NOT EXISTS idx_predictions_race_date ON predictions(race_date);
CREATE INDEX IF NOT EXISTS idx_learning_race_id ON learning_history(race_id);
CREATE INDEX IF NOT EXISTS idx_learning_analyzed_at ON learning_history(analyzed_at);

-- コメント
COMMENT ON TABLE predictions IS '競馬予想結果を保存（Phase 0-2）';
COMMENT ON TABLE learning_history IS '予想結果の分析・学習履歴';
COMMENT ON COLUMN learning_history.learning_points IS 'LLMプロンプトで使用する学習ポイント';
