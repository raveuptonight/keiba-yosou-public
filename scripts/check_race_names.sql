-- レース名を検索して実際のデータを確認
-- 日本ダービーが見つからない理由を調査

-- 「ダービー」を含むレース名を検索
SELECT
    kyosomei_hondai,
    COUNT(*) as race_count,
    MIN(kaisai_nen) as first_year,
    MAX(kaisai_nen) as last_year
FROM race_shosai
WHERE kyosomei_hondai LIKE '%ダービー%'
  AND data_kubun = '7'
GROUP BY kyosomei_hondai
ORDER BY race_count DESC
LIMIT 20;

-- 「日本」を含むレース名を検索
SELECT
    kyosomei_hondai,
    COUNT(*) as race_count,
    MIN(kaisai_nen) as first_year,
    MAX(kaisai_nen) as last_year
FROM race_shosai
WHERE kyosomei_hondai LIKE '%日本%'
  AND data_kubun = '7'
GROUP BY kyosomei_hondai
ORDER BY race_count DESC
LIMIT 20;

-- 「東京優駿」を含むレース名を検索（日本ダービーの正式名称）
SELECT
    race_code,
    kyosomei_hondai,
    kaisai_nen,
    kaisai_gappi,
    keibajo_code,
    grade_code
FROM race_shosai
WHERE kyosomei_hondai LIKE '%東京優駿%'
  AND data_kubun = '7'
ORDER BY kaisai_nen DESC, kaisai_gappi DESC
LIMIT 10;

-- 最近の主要G1レースを確認
SELECT
    kyosomei_hondai,
    kaisai_nen,
    kaisai_gappi
FROM race_shosai
WHERE grade_code = 'A'
  AND data_kubun = '7'
  AND kaisai_nen >= '2024'
ORDER BY kaisai_nen DESC, kaisai_gappi DESC
LIMIT 30;
