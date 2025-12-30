-- 未勝利戦などレース名が空欄または短いレースを確認

-- レース名が空欄のレースを検索
SELECT
    race_code,
    kyosomei_hondai,
    LENGTH(kyosomei_hondai) as name_length,
    kaisai_nen,
    kaisai_gappi,
    keibajo_code,
    grade_code,
    kyoso_shubetsu_code
FROM race_shosai
WHERE data_kubun = '7'
  AND (
    kyosomei_hondai IS NULL
    OR kyosomei_hondai = ''
    OR TRIM(kyosomei_hondai) = ''
    OR LENGTH(TRIM(kyosomei_hondai)) < 3
  )
  AND kaisai_nen >= '2024'
ORDER BY kaisai_nen DESC, kaisai_gappi DESC
LIMIT 20;

-- 未勝利戦のレース名パターンを確認
SELECT
    kyosomei_hondai,
    COUNT(*) as count
FROM race_shosai
WHERE data_kubun = '7'
  AND kaisai_nen >= '2024'
  AND (
    kyosomei_hondai LIKE '%未勝利%'
    OR kyosomei_hondai LIKE '%新馬%'
    OR kyosomei_hondai LIKE '%1勝%'
    OR kyosomei_hondai LIKE '%2勝%'
  )
GROUP BY kyosomei_hondai
ORDER BY count DESC
LIMIT 20;

-- 条件戦のレース名を確認
SELECT
    race_code,
    kyosomei_hondai,
    kaisai_nen,
    kaisai_gappi,
    keibajo_code,
    grade_code
FROM race_shosai
WHERE data_kubun = '7'
  AND kaisai_nen = '2025'
  AND grade_code NOT IN ('A', 'B', 'C', 'D')  -- G1,G2,G3,Listed以外
ORDER BY kaisai_nen DESC, kaisai_gappi DESC
LIMIT 20;
