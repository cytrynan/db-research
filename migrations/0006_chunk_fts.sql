-- ① 探し物（全文検索側）。日本語はアプリ側（SudachiPy）で分かち書きして lexemes に入れ、
-- 生成列 tsv は 'simple' 辞書で語をそのまま索引する（拡張なし＝どの PostgreSQL でも同じ）
ALTER TABLE chunk ADD COLUMN lexemes text NOT NULL DEFAULT '';
ALTER TABLE chunk ADD COLUMN tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', lexemes)) STORED;
CREATE INDEX chunk_tsv_gin ON chunk USING gin (tsv);
