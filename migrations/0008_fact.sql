-- ③ 時点（F5）: 事実に有効時間（valid_from / valid_to）と記録時間（recorded_at）を持たせる。
-- OKF には有効時間のキーが無い（D-10）ので、独自キー valid と本文の日付表現から機械抽出する。
-- 古い事実は消さず valid_to を閉じる（この単位では自動で閉じない＝NULL のまま）。
CREATE TABLE fact (
    id            bigserial PRIMARY KEY,
    document_id   bigint      NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    chunk_id      bigint      REFERENCES chunk(id) ON DELETE CASCADE,
    subject       text        NOT NULL,
    value         text        NOT NULL,
    valid_from    timestamptz NOT NULL,
    valid_to      timestamptz,
    recorded_at   timestamptz NOT NULL,
    valid_source  text        NOT NULL
                  CHECK (valid_source IN ('explicit', 'dated_text', 'inferred')),
    lexemes       text        NOT NULL DEFAULT '',
    tsv           tsvector    GENERATED ALWAYS AS (to_tsvector('simple', lexemes)) STORED,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

-- 同じ行に同じ日付が 2 回出ても 1 件（識別子契約「衝突」）
CREATE UNIQUE INDEX fact_uniq
    ON fact (document_id, COALESCE(chunk_id, 0), subject, valid_from);
CREATE INDEX fact_tsv_gin   ON fact USING gin (tsv);
CREATE INDEX fact_valid_idx ON fact (valid_from, valid_to);
