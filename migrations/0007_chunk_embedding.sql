-- 方式別の埋め込み。同じ断片に variant（plain / ctx）× model の組で複数行を持てる
-- 次元は既定モデル intfloat/multilingual-e5-small の 384（別次元のモデルは別表にする）
CREATE TABLE chunk_embedding (
    chunk_id   bigint NOT NULL REFERENCES chunk(id) ON DELETE CASCADE,
    variant    text   NOT NULL CHECK (variant IN ('plain', 'ctx')),
    model      text   NOT NULL,
    embedding  vector(384) NOT NULL,
    PRIMARY KEY (chunk_id, variant, model)
);

-- cosine。ef_search は検索時に SET LOCAL で振る（40 / 100 / 250 を測る）
CREATE INDEX chunk_embedding_hnsw
    ON chunk_embedding USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
