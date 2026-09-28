-- 見出し単位の断片。tsv 生成列と埋め込みは次の作業単位（分かち書き方式と同時に決める）
CREATE TABLE chunk (
    id            bigserial PRIMARY KEY,
    document_id   bigint  NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    ordinal       int     NOT NULL,
    heading_path  text    NOT NULL DEFAULT '',
    body          text    NOT NULL,
    context       text,
    tokens        int     NOT NULL,
    UNIQUE (document_id, ordinal)
);

CREATE INDEX chunk_document_idx ON chunk (document_id);
