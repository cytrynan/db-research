-- 1 Markdown ファイル = 1 行。フロントマターは jsonb に丸ごと、よく使うキーだけ列に出す
CREATE TABLE document (
    id            bigserial PRIMARY KEY,
    bundle        text        NOT NULL,
    rel_path      text        NOT NULL,
    format        text        NOT NULL CHECK (format IN ('okf', 'kuroko')),
    fm            jsonb       NOT NULL,
    type          text,
    status        text        NOT NULL DEFAULT 'stable',
    generated_at  timestamptz,
    verified_at   timestamptz,
    stale_after   date,
    content_hash  text        NOT NULL,
    ingested_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (bundle, rel_path)
);

CREATE INDEX document_type_idx   ON document (bundle, type);
CREATE INDEX document_status_idx ON document (bundle, status);

-- private.md は二重防御の DB 側。走査で除外しても、直接 INSERT しても入らない
CREATE OR REPLACE FUNCTION reject_private_md() RETURNS trigger AS $$
BEGIN
    IF NEW.rel_path = 'private.md' OR NEW.rel_path LIKE '%/private.md' THEN
        RAISE EXCEPTION 'private.md is never ingested (rel_path=%)', NEW.rel_path
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER document_reject_private_md
    BEFORE INSERT OR UPDATE ON document
    FOR EACH ROW EXECUTE FUNCTION reject_private_md();
