-- ===========================================
-- マイグレーション: predictions テーブル作成
-- ===========================================
-- 作成日: 2024-12-28
-- 説明: LLM予想結果を保存するテーブル

-- predictions テーブル作成
CREATE TABLE IF NOT EXISTS predictions (
    -- 主キー
    prediction_id TEXT PRIMARY KEY,

    -- レース情報
    race_id TEXT NOT NULL,
    race_name TEXT NOT NULL,
    race_date TEXT NOT NULL,
    venue TEXT NOT NULL,
    race_number TEXT NOT NULL,
    race_time TEXT NOT NULL,

    -- 予想種別
    is_final BOOLEAN NOT NULL DEFAULT FALSE,

    -- 投資情報
    total_investment INTEGER NOT NULL,
    expected_return INTEGER NOT NULL,
    expected_roi FLOAT NOT NULL,

    -- 予想結果（JSONB形式で保存）
    prediction_result JSONB NOT NULL,

    -- メタデータ
    predicted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- インデックス作成
CREATE INDEX IF NOT EXISTS idx_predictions_race_id
    ON predictions (race_id);

CREATE INDEX IF NOT EXISTS idx_predictions_race_date
    ON predictions (race_date DESC);

CREATE INDEX IF NOT EXISTS idx_predictions_is_final
    ON predictions (is_final);

CREATE INDEX IF NOT EXISTS idx_predictions_predicted_at
    ON predictions (predicted_at DESC);

-- 複合インデックス（レースID + 予想種別）
CREATE INDEX IF NOT EXISTS idx_predictions_race_final
    ON predictions (race_id, is_final);

-- JSONB フィールドのインデックス
CREATE INDEX IF NOT EXISTS idx_predictions_result_gin
    ON predictions USING GIN (prediction_result);

-- コメント追加
COMMENT ON TABLE predictions IS 'LLM予想結果を保存するテーブル';
COMMENT ON COLUMN predictions.prediction_id IS '予想ID（UUID形式）';
COMMENT ON COLUMN predictions.race_id IS 'レースID（16桁）';
COMMENT ON COLUMN predictions.is_final IS '最終予想フラグ（馬体重反映後）';
COMMENT ON COLUMN predictions.prediction_result IS '予想結果JSON（win_prediction, betting_strategy）';
COMMENT ON COLUMN predictions.expected_roi IS '期待ROI（回収率）';

-- 更新日時自動更新トリガー
CREATE OR REPLACE FUNCTION update_predictions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_predictions_updated_at
    BEFORE UPDATE ON predictions
    FOR EACH ROW
    EXECUTE FUNCTION update_predictions_updated_at();

-- サンプルデータ挿入（開発用）
-- INSERT INTO predictions (
--     prediction_id,
--     race_id,
--     race_name,
--     race_date,
--     venue,
--     race_number,
--     race_time,
--     is_final,
--     total_investment,
--     expected_return,
--     expected_roi,
--     prediction_result
-- ) VALUES (
--     'abc123def456',
--     '202412280506',
--     '中山金杯',
--     '2024-12-28',
--     '中山',
--     '11R',
--     '15:25',
--     false,
--     10000,
--     15000,
--     1.5,
--     '{
--         "win_prediction": {
--             "first": {"horse_number": 3, "horse_name": "ディープボンド", "expected_odds": 3.5, "confidence": 0.85},
--             "second": {"horse_number": 7, "horse_name": "エフフォーリア", "expected_odds": 5.2, "confidence": 0.72},
--             "third": {"horse_number": 12, "horse_name": "タイトルホルダー", "expected_odds": 8.1, "confidence": 0.65}
--         },
--         "betting_strategy": {
--             "recommended_tickets": [
--                 {"ticket_type": "3連複", "numbers": [3, 7, 12], "amount": 1000, "expected_payout": 8500}
--             ]
--         }
--     }'::jsonb
-- );
