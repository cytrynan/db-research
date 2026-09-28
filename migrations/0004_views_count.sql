-- ② 数える: 集計の定義をビューに固定する（毎回同じ数字を返すため。PRD F4）

CREATE OR REPLACE VIEW v_by_bundle AS
SELECT d.bundle,
       count(DISTINCT d.id) AS docs,
       count(c.id)          AS chunks
FROM document d
LEFT JOIN chunk c ON c.document_id = d.id
GROUP BY d.bundle
ORDER BY d.bundle;

CREATE OR REPLACE VIEW v_by_type AS
SELECT bundle, type, count(*) AS n
FROM document
GROUP BY bundle, type
ORDER BY bundle, type NULLS LAST;

CREATE OR REPLACE VIEW v_unverified AS
SELECT bundle, count(*) AS n
FROM document
WHERE verified_at IS NULL AND status <> 'deprecated'
GROUP BY bundle
ORDER BY bundle;

CREATE OR REPLACE VIEW v_stale AS
SELECT bundle, count(*) AS n
FROM document
WHERE stale_after IS NOT NULL AND stale_after < current_date
GROUP BY bundle
ORDER BY bundle;
