"""`dbr sync`（features/sync）: 変更・新規・削除の反映と、無変更で何も動かないこと.

正本フォルダは tmp_path に fixtures をコピーして模す（実データには触れない）。
埋め込みは FakeEmbedder。件数はすべて SQL で数える。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from dbr.features.sync import (
    BundleSyncReport,
    SyncReport,
    prune,
    run_sync,
    summaries_stale,
)
from dbr.shared.db import connect
from dbr.shared.embed.fake import FakeEmbedder
from tests.integration.conftest import FIXTURES

pytestmark = pytest.mark.db

EMB = FakeEmbedder()


def _quiet(_msg: str) -> None:
    return None


def _sync(dsn: str, roots: dict[str, Path], **kw: Any) -> SyncReport:
    return run_sync(dsn, EMB, roots=roots, log=_quiet, **kw)


def _col(dsn: str, sql: str, params: dict[str, Any] | None = None) -> list[Any]:
    """1 列目の値のリスト（`SELECT x ...` の x）."""
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return [next(iter(r.values())) for r in cur.fetchall()]


def _n(dsn: str, sql: str, params: dict[str, Any] | None = None) -> int:
    """`SELECT count(*) ...` の値."""
    (value,) = _col(dsn, sql, params)
    return int(str(value))


def _doc_id(dsn: str, bundle: str, rel: str) -> int:
    ids = _col(
        dsn,
        "SELECT id FROM document WHERE bundle=%(b)s AND rel_path=%(r)s",
        {"b": bundle, "r": rel},
    )
    assert len(ids) == 1, f"{bundle}/{rel} が DB に {len(ids)} 行"
    return int(str(ids[0]))


def _chunk_ids(dsn: str, doc_id: int) -> list[int]:
    rows = _col(
        dsn,
        "SELECT id FROM chunk WHERE document_id=%(d)s ORDER BY ordinal",
        {"d": doc_id},
    )
    return [int(str(i)) for i in rows]


def _chunk_total(dsn: str) -> int:
    return _n(dsn, "SELECT count(*) FROM chunk")


def _embedding_total(dsn: str) -> int:
    return _n(dsn, "SELECT count(*) FROM chunk_embedding")


def _doc_count(dsn: str, bundle: str | None = None) -> int:
    if bundle is None:
        return _n(dsn, "SELECT count(*) FROM document")
    return _n(dsn, "SELECT count(*) FROM document WHERE bundle=%(b)s", {"b": bundle})


def _tree(src: str, tmp_path: Path, name: str = "dev") -> Path:
    dst = tmp_path / name
    shutil.copytree(FIXTURES / src, dst)
    return dst


def _rep(report: SyncReport, bundle: str) -> BundleSyncReport:
    got = [b for b in report.bundles if b.bundle == bundle]
    assert len(got) == 1
    return got[0]


# ① 初回 sync ---------------------------------------------------------------


def test_first_sync_fills_document_chunk_embedding_fact_summary(
    clean_db: str, tmp_path: Path
) -> None:
    root = _tree("okf-plain", tmp_path)  # alpha / beta / notype
    report = _sync(clean_db, {"dev": root})

    assert [b.bundle for b in report.bundles] == ["dev"]
    rep = report.bundles[0]
    assert (rep.inserted, rep.updated, rep.unchanged, rep.pruned) == (3, 0, 0, 0)
    assert (rep.failed, rep.skipped_missing_root) == (0, False)
    assert report.changed() is True

    assert _doc_count(clean_db) == 3
    chunks = _chunk_total(clean_db)
    assert chunks > 0
    # 断片ごとに plain と ctx の 2 variant
    for variant in ("plain", "ctx"):
        n = _n(
            clean_db,
            "SELECT count(*) FROM chunk_embedding WHERE variant=%(v)s",
            {"v": variant},
        )
        assert n == chunks, variant
    assert _embedding_total(clean_db) == chunks * 2
    assert (rep.embedded_plain, rep.embedded_ctx) == (chunks, chunks)

    # fact: alpha・beta は generated から inferred 1 件ずつ、notype は日付無しで 0 件
    assert rep.facts is not None and rep.summaries is not None
    assert rep.rebuilt_reason == "changed"
    facts = _n(clean_db, "SELECT count(*) FROM fact")
    assert (
        facts == rep.facts["explicit"] + rep.facts["dated_text"] + rep.facts["inferred"]
    )
    assert facts == 2 and rep.facts["inferred"] == 2

    # summary: bundle 1 + document 3 + section は断片の数だけ
    def summaries(level: str) -> int:
        return _n(
            clean_db, "SELECT count(*) FROM summary WHERE level=%(l)s", {"l": level}
        )

    assert summaries("bundle") == 1
    assert (
        _n(
            clean_db,
            "SELECT count(*) FROM summary WHERE level='bundle' AND target_key='dev'",
        )
        == 1
    )
    assert summaries("document") == 3
    assert summaries("section") == chunks
    assert (rep.summaries["documents"], rep.summaries["sections"]) == (3, chunks)


# ② 内容変更 ----------------------------------------------------------------

ALPHA_V2 = """---
type: Note
generated: { by: sample/agent-1, at: 2026-09-01T10:00:00+09:00 }
---

# Alpha v2

書き換えた導入。

## 一

本文その一。

## 二

本文その二。

## 三

本文その三。
"""


def test_changed_file_replaces_chunks_and_embeddings(
    clean_db: str, tmp_path: Path
) -> None:
    root = _tree("okf-plain", tmp_path)
    _sync(clean_db, {"dev": root})
    alpha_id = _doc_id(clean_db, "dev", "alpha.md")
    hash_sql = "SELECT content_hash FROM document WHERE id=%(d)s"
    old_hash = _col(clean_db, hash_sql, {"d": alpha_id})[0]
    old_chunks = _chunk_ids(clean_db, alpha_id)
    others_sql = "SELECT id FROM chunk WHERE document_id <> %(d)s ORDER BY id"
    other_chunks = _col(clean_db, others_sql, {"d": alpha_id})
    assert len(old_chunks) == 3 and other_chunks  # 書き換え前の断片（alpha は 3 つ）

    (root / "alpha.md").write_text(ALPHA_V2, encoding="utf-8")
    report = _sync(clean_db, {"dev": root})
    rep = report.bundles[0]

    assert (rep.inserted, rep.updated, rep.unchanged, rep.pruned) == (0, 1, 2, 0)
    assert _col(clean_db, hash_sql, {"d": alpha_id})[0] != old_hash
    assert _doc_count(clean_db) == 3  # 重複していない

    new_chunks = _chunk_ids(clean_db, alpha_id)
    assert len(new_chunks) == 4  # 導入 + 一・二・三
    assert not set(new_chunks) & set(old_chunks)
    # 古い断片とその埋め込みが残らない
    ids = {"ids": old_chunks}
    assert _n(clean_db, "SELECT count(*) FROM chunk WHERE id = ANY(%(ids)s)", ids) == 0
    assert (
        _n(
            clean_db,
            "SELECT count(*) FROM chunk_embedding WHERE chunk_id = ANY(%(ids)s)",
            ids,
        )
        == 0
    )
    # 変更の無かった文書の断片は作り直されていない
    assert _col(clean_db, others_sql, {"d": alpha_id}) == other_chunks
    # 断片数＝新しい断片数、埋め込み数＝断片数×2、新しく計算したのは新断片だけ
    total = _chunk_total(clean_db)
    assert _embedding_total(clean_db) == total * 2
    assert (rep.embedded_plain, rep.embedded_ctx) == (4, 4)
    # 古い断片の section 要約も残らない（summary は FK 無し）
    keys = {"ids": [str(i) for i in old_chunks]}
    assert (
        _n(
            clean_db,
            "SELECT count(*) FROM summary WHERE level='section' AND target_key = ANY(%(ids)s)",
            keys,
        )
        == 0
    )
    assert _n(clean_db, "SELECT count(*) FROM summary WHERE level='section'") == total
    assert rep.facts is not None and rep.summaries is not None
    assert rep.rebuilt_reason == "changed"


# ③ 削除 --------------------------------------------------------------------


def test_deleted_file_removes_document_and_everything_under_it(
    clean_db: str, tmp_path: Path
) -> None:
    root = _tree("dated", tmp_path)
    _sync(clean_db, {"dev": root})
    gone = "decisions-note.md"  # chunk に紐づく dated_text の fact を持つ文書
    doc_id = _doc_id(clean_db, "dev", gone)
    chunk_ids = _chunk_ids(clean_db, doc_id)
    d = {"d": doc_id}
    c = {"c": chunk_ids}
    k = {"k": str(doc_id)}
    sec = {"k": [str(i) for i in chunk_ids]}
    docs_before = _doc_count(clean_db)

    # 空振りの確認（消す前は全部ある）
    assert len(chunk_ids) >= 2
    emb = "SELECT count(*) FROM chunk_embedding WHERE chunk_id = ANY(%(c)s)"
    assert _n(clean_db, emb, c) == len(chunk_ids) * 2
    assert _n(clean_db, "SELECT count(*) FROM fact WHERE document_id=%(d)s", d) >= 3
    chunk_facts = (
        "SELECT count(*) FROM fact WHERE document_id=%(d)s AND chunk_id IS NOT NULL"
    )
    assert _n(clean_db, chunk_facts, d) >= 3
    doc_sum = "SELECT count(*) FROM summary WHERE level='document' AND target_key=%(k)s"
    sec_sum = (
        "SELECT count(*) FROM summary WHERE level='section' AND target_key = ANY(%(k)s)"
    )
    assert _n(clean_db, doc_sum, k) == 1
    assert _n(clean_db, sec_sum, sec) == len(chunk_ids)

    (root / gone).unlink()
    report = _sync(clean_db, {"dev": root})
    rep = report.bundles[0]

    assert (rep.inserted, rep.updated, rep.pruned) == (0, 0, 1)
    assert rep.unchanged == docs_before - 1
    assert report.changed() is True
    assert rep.facts is not None and rep.summaries is not None  # 削除も「変更」
    assert rep.rebuilt_reason == "changed"
    assert _n(clean_db, "SELECT count(*) FROM document WHERE id=%(d)s", d) == 0
    assert _doc_count(clean_db) == docs_before - 1
    assert _n(clean_db, "SELECT count(*) FROM chunk WHERE document_id=%(d)s", d) == 0
    assert _n(clean_db, emb, c) == 0
    assert _n(clean_db, "SELECT count(*) FROM fact WHERE document_id=%(d)s", d) == 0
    assert _n(clean_db, doc_sum, k) == 0
    assert _n(clean_db, sec_sum, sec) == 0
    # 残った文書の要約は数が合う
    assert _n(clean_db, "SELECT count(*) FROM summary WHERE level='document'") == (
        docs_before - 1
    )
    assert _n(clean_db, "SELECT count(*) FROM summary WHERE level='section'") == (
        _chunk_total(clean_db)
    )
    assert _embedding_total(clean_db) == _chunk_total(clean_db) * 2


def test_prune_alone_is_scoped_to_its_bundle_and_clears_summaries(
    clean_db: str, tmp_path: Path
) -> None:
    dev = _tree("okf-plain", tmp_path, "dev")
    tax = _tree("dated", tmp_path, "tax")
    _sync(clean_db, {"dev": dev, "tax": tax})
    assert _doc_count(clean_db, "tax") == 4
    beta_id = _doc_id(clean_db, "dev", "beta.md")
    beta_chunks = [str(i) for i in _chunk_ids(clean_db, beta_id)]
    assert beta_chunks
    doc_sum = "SELECT count(*) FROM summary WHERE level='document' AND target_key=%(k)s"
    sec_sum = (
        "SELECT count(*) FROM summary WHERE level='section' AND target_key = ANY(%(k)s)"
    )
    assert _n(clean_db, doc_sum, {"k": str(beta_id)}) == 1
    assert _n(clean_db, sec_sum, {"k": beta_chunks}) == len(beta_chunks)
    summaries_before = _n(clean_db, "SELECT count(*) FROM summary")

    (dev / "beta.md").unlink()
    assert prune(clean_db, "dev", dev) == 1
    assert prune(clean_db, "dev", dev) == 0  # 2 回目は何も消さない
    assert _doc_count(clean_db, "dev") == 2
    assert _doc_count(clean_db, "tax") == 4  # 他 bundle は触らない
    # summary は FK が無いので prune が自分で消す（run_summarize の掃除に頼らない）
    assert _n(clean_db, doc_sum, {"k": str(beta_id)}) == 0
    assert _n(clean_db, sec_sum, {"k": beta_chunks}) == 0
    assert _n(clean_db, "SELECT count(*) FROM summary") == (
        summaries_before
        - 1
        - len(beta_chunks)  # document 1 + section 数。bundle 階層は残る
    )


# ④ 無変更 ------------------------------------------------------------------


def test_second_sync_changes_nothing(clean_db: str, tmp_path: Path) -> None:
    roots = {
        "dev": _tree("okf-plain", tmp_path, "dev"),
        "tax": _tree("dated", tmp_path, "tax"),
    }
    _sync(clean_db, roots)

    def snapshot() -> dict[str, list[Any]]:
        return {
            "document": _col(clean_db, "SELECT id FROM document ORDER BY id"),
            "chunk": _col(clean_db, "SELECT id FROM chunk ORDER BY id"),
            "embedding": _col(
                clean_db,
                "SELECT chunk_id::text || variant AS k FROM chunk_embedding ORDER BY 1",
            ),
            "fact": _col(clean_db, "SELECT id FROM fact ORDER BY id"),
            "summary": _col(clean_db, "SELECT id FROM summary ORDER BY id"),
        }

    before = snapshot()
    assert all(before.values())
    report = _sync(clean_db, roots)

    assert len(report.bundles) == 2
    for rep in report.bundles:
        assert (rep.inserted, rep.updated, rep.pruned) == (0, 0, 0), rep.bundle
        assert (rep.embedded_plain, rep.embedded_ctx) == (0, 0), rep.bundle
        assert rep.facts is None and rep.summaries is None, rep.bundle
        assert rep.rebuilt_reason is None, rep.bundle
        assert rep.changed() is False
    assert [b.unchanged for b in report.bundles] == [3, 4]
    assert report.changed() is False
    assert report.to_dict()["changed"] is False
    assert snapshot() == before  # 行（id）まで同一＝作り直していない


# ⑤ 正本フォルダが無い --------------------------------------------------------


def test_missing_root_is_skipped_without_exception(
    clean_db: str, tmp_path: Path
) -> None:
    report = _sync(clean_db, {"dev": tmp_path / "does-not-exist"})
    rep = report.bundles[0]
    assert rep.skipped_missing_root is True
    assert (rep.inserted, rep.updated, rep.unchanged, rep.pruned) == (0, 0, 0, 0)
    assert rep.facts is None and rep.summaries is None
    assert rep.rebuilt_reason is None
    assert report.changed() is False
    assert _doc_count(clean_db) == 0


def test_missing_root_does_not_wipe_existing_documents(
    clean_db: str, tmp_path: Path
) -> None:
    root = _tree("okf-plain", tmp_path)
    _sync(clean_db, {"dev": root})
    assert _doc_count(clean_db, "dev") == 3

    # 未マウント等で正本が見えない ≠ 全文書が消えた
    shutil.rmtree(root)
    report = _sync(clean_db, {"dev": root})
    assert report.bundles[0].skipped_missing_root is True
    assert report.bundles[0].pruned == 0
    with pytest.raises(ValueError, match="存在しません"):
        prune(clean_db, "dev", root)
    assert _doc_count(clean_db, "dev") == 3


# ⑥ bundles で絞る ------------------------------------------------------------


def test_bundles_argument_limits_the_targets(clean_db: str, tmp_path: Path) -> None:
    roots = {
        "tax": _tree("dated", tmp_path, "tax"),
        "dev": _tree("okf-plain", tmp_path, "dev"),
    }
    report = _sync(clean_db, roots, bundles=["dev"])
    assert [b.bundle for b in report.bundles] == ["dev"]
    assert _doc_count(clean_db, "dev") == 3
    assert _doc_count(clean_db, "tax") == 0
    assert _n(clean_db, "SELECT count(*) FROM summary WHERE target_key='tax'") == 0

    # 絞らなければ roots にある bundle を台帳の順（dev → tax）に処理する
    both = _sync(clean_db, roots)
    assert [b.bundle for b in both.bundles] == ["dev", "tax"]
    assert [b.unchanged for b in both.bundles] == [3, 0]
    assert _rep(both, "tax").inserted == 4
    assert _doc_count(clean_db, "tax") == 4


def test_unknown_bundle_or_bundle_without_root_is_a_value_error(
    clean_db: str, tmp_path: Path
) -> None:
    root = _tree("okf-plain", tmp_path)
    with pytest.raises(ValueError, match="語彙外"):
        _sync(clean_db, {"dev": root}, bundles=["nonexistent"])
    with pytest.raises(ValueError, match="未指定"):
        _sync(clean_db, {"dev": root}, bundles=["tax"])
    assert _doc_count(clean_db) == 0  # 検査は DB に触れる前


# ⑦ 途中で落ちた跡（変更は無いが要約が欠けている・古い）---------------------------


@pytest.mark.parametrize(
    "crash",
    [
        "DELETE FROM summary WHERE level='bundle' AND target_key='dev'",
        "DELETE FROM summary WHERE level='document'",
        "UPDATE summary SET source_hash='stale' WHERE level='document'",
    ],
    ids=["bundle-row-missing", "document-rows-missing", "document-hash-changed"],
)
def test_sync_rebuilds_facts_and_summaries_after_a_crash_then_settles(
    clean_db: str, tmp_path: Path, crash: str
) -> None:
    root = _tree("okf-plain", tmp_path)
    first = _sync(clean_db, {"dev": root})
    assert first.bundles[0].rebuilt_reason == "changed"
    assert _n(clean_db, "SELECT count(*) FROM summary WHERE level='bundle'") == 1
    docs, chunks = _doc_count(clean_db), _chunk_total(clean_db)

    # ingest の後・summarize の前に落ちた状態を模す（正本のファイルは変えない）
    conn = connect(clean_db)
    with conn, conn.cursor() as cur:
        cur.execute(crash)
    assert summaries_stale(clean_db, "dev") is True

    second = _sync(clean_db, {"dev": root})
    rep = second.bundles[0]
    assert (rep.inserted, rep.updated, rep.pruned, rep.unchanged) == (0, 0, 0, 3)
    assert rep.changed() is False and second.changed() is False  # 文書は動いていない
    assert rep.rebuilt_reason == "stale_summaries"
    assert rep.facts is not None and rep.summaries is not None
    assert second.to_dict()["bundles"][0]["rebuilt_reason"] == "stale_summaries"
    # 要約が揃い直した
    assert _n(clean_db, "SELECT count(*) FROM summary WHERE level='bundle'") == 1
    assert _n(clean_db, "SELECT count(*) FROM summary WHERE level='document'") == docs
    assert _n(clean_db, "SELECT count(*) FROM summary WHERE level='section'") == chunks
    assert summaries_stale(clean_db, "dev") is False
    # 文書側は触っていない
    assert (_doc_count(clean_db), _chunk_total(clean_db)) == (docs, chunks)

    # 直った後の 3 回目は再び何もしない（冪等に戻る）
    third = _sync(clean_db, {"dev": root})
    assert third.bundles[0].rebuilt_reason is None
    assert third.bundles[0].facts is None and third.bundles[0].summaries is None
    assert third.changed() is False


# その他: 追加・改名・private.md ------------------------------------------------


def test_added_and_renamed_files(clean_db: str, tmp_path: Path) -> None:
    root = _tree("okf-plain", tmp_path)
    _sync(clean_db, {"dev": root})
    kept = _chunk_ids(clean_db, _doc_id(clean_db, "dev", "alpha.md")) + _chunk_ids(
        clean_db, _doc_id(clean_db, "dev", "notype.md")
    )

    (root / "gamma.md").write_text(
        "---\ntype: Note\n---\n# Gamma\n\n新規。\n", encoding="utf-8"
    )
    (root / "beta.md").rename(root / "beta2.md")  # 改名 = 削除 + 追加
    report = _sync(clean_db, {"dev": root})
    rep = report.bundles[0]

    assert (rep.inserted, rep.updated, rep.pruned, rep.unchanged) == (2, 0, 1, 2)
    assert _col(clean_db, "SELECT rel_path FROM document ORDER BY rel_path") == [
        "alpha.md",
        "beta2.md",
        "gamma.md",
        "notype.md",
    ]
    total = _chunk_total(clean_db)
    assert _embedding_total(clean_db) == total * 2
    # 新しく計算したのは、残った断片（alpha・notype）以外の全部
    assert rep.embedded_plain == rep.embedded_ctx == total - len(kept)


def test_private_md_and_backups_never_enter_and_do_not_count_as_changes(
    clean_db: str, tmp_path: Path
) -> None:
    root = _tree(
        "with-private", tmp_path
    )  # ok.md / private.md（.bak-… は *.md に当たらず走査に出ない）
    report = _sync(clean_db, {"dev": root})
    rep = report.bundles[0]

    assert (rep.inserted, rep.excluded, rep.pruned) == (1, 1, 0)
    assert _col(clean_db, "SELECT rel_path FROM document") == ["ok.md"]
    assert (
        _n(clean_db, "SELECT count(*) FROM document WHERE rel_path ILIKE '%private%'")
        == 0
    )
    again = _sync(clean_db, {"dev": root})
    assert again.changed() is False and again.bundles[0].excluded == 1
