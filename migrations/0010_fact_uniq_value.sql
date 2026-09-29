-- 受入検証 D3（2026-09-29）: 見出しが同じで日付＋動詞しか違わない別々の行が、subject が同じために
-- 1 件に畳まれていた（実データで 2 行。dev 更新ログの同日・同ファイルの Update 2 件など）。
-- 事実の識別子に行の内容 md5(value) を加える。「同じ行に同じ日付が 2 回出ても 1 件」
-- （識別子契約「衝突」）は value が同じなので引き続き成り立つ。
DROP INDEX fact_uniq;
CREATE UNIQUE INDEX fact_uniq
    ON fact (document_id, COALESCE(chunk_id, 0), subject, valid_from, md5(value));
