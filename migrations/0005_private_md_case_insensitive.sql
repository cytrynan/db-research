-- 2026-09-29 受入検証の指摘: `Private.md` が走査・トリガーの完全一致をすり抜けた。
-- Windows の FS は大文字小文字を区別しないので、トリガー側も lower() で比較する。
-- 既存の 0002 は編集しない（関数を置き換えるだけ。トリガーはそのまま同じ関数を呼ぶ）。
CREATE OR REPLACE FUNCTION reject_private_md() RETURNS trigger AS $$
BEGIN
    IF lower(NEW.rel_path) = 'private.md' OR lower(NEW.rel_path) LIKE '%/private.md' THEN
        RAISE EXCEPTION 'private.md is never ingested (rel_path=%)', NEW.rel_path
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
