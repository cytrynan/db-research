-- ② 数える: 「確認済み（verified）の件数」を補集合でなく定義そのもので数える
-- （受入検証 2026-09-29・Q12 が v_unverified の補集合で答えていた分の回収）。
CREATE OR REPLACE VIEW v_verified AS
SELECT bundle, count(*) AS n
FROM document
WHERE verified_at IS NOT NULL
GROUP BY bundle
ORDER BY bundle;
