-- ④ 全体（F6）: 要約の階層（bundle → document → section）。抽出型（LLM なし・決定的）で始める。
-- target_key は生成側が組み立てる（bundle 名 / document.id / chunk.id の文字列）。
CREATE TABLE summary (
    id           bigserial PRIMARY KEY,
    level        text   NOT NULL CHECK (level IN ('bundle', 'document', 'section')),
    target_key   text   NOT NULL,
    text         text   NOT NULL,
    source_hash  text   NOT NULL,
    tokens       int    NOT NULL,
    method       text   NOT NULL DEFAULT 'extractive',
    UNIQUE (level, target_key)
);
