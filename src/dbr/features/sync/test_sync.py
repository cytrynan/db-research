"""sync のユニット（DB 不要）: 台帳 bundle_roots と、報告の集計・辞書化."""

from pathlib import Path

import pytest

from dbr.features.ingest.handler import BUNDLES
from dbr.features.sync import (
    BUNDLES_ORDER,
    BundleSyncReport,
    SyncReport,
    bundle_roots,
    run_sync,
)


@pytest.fixture(autouse=True)
def _no_root_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """開発者の環境変数に左右されないよう、上書き用の変数を全部外す."""
    for bundle in BUNDLES_ORDER:
        monkeypatch.delenv(f"DBR_ROOT_{bundle.upper()}", raising=False)


def test_order_covers_exactly_the_ingest_vocabulary() -> None:
    assert set(BUNDLES_ORDER) == set(BUNDLES)
    assert len(BUNDLES_ORDER) == len(set(BUNDLES_ORDER)) == 7


def test_bundle_roots_defaults_for_all_seven_bundles() -> None:
    home = Path.home()
    roots = bundle_roots()
    assert list(roots) == list(BUNDLES_ORDER)  # 台帳の順
    assert roots["references"] == home / ".claude" / "references"
    assert roots["memory"] == (
        home / ".claude" / "projects" / "C--Users-meer0" / "memory"
    )
    for bundle in ("dev", "stock", "tax", "scout", "experiments"):
        assert roots[bundle] == home / ".agents" / "knowledge" / bundle


def test_bundle_roots_env_override_only_that_bundle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DBR_ROOT_MEMORY", str(tmp_path / "mem"))
    monkeypatch.setenv("DBR_ROOT_SCOUT", str(tmp_path / "sc"))
    roots = bundle_roots()
    assert roots["memory"] == tmp_path / "mem"
    assert roots["scout"] == tmp_path / "sc"
    assert roots["dev"] == Path.home() / ".agents" / "knowledge" / "dev"  # 他は既定


def test_bundle_roots_empty_env_value_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DBR_ROOT_DEV", "")
    assert bundle_roots()["dev"] == Path.home() / ".agents" / "knowledge" / "dev"


def _rep(
    bundle: str,
    *,
    inserted: int = 0,
    updated: int = 0,
    pruned: int = 0,
    unchanged: int = 0,
    excluded: int = 0,
    failed: int = 0,
    embedded_plain: int = 0,
    embedded_ctx: int = 0,
) -> BundleSyncReport:
    return BundleSyncReport(
        bundle=bundle,
        root=f"/x/{bundle}",
        inserted=inserted,
        updated=updated,
        pruned=pruned,
        unchanged=unchanged,
        excluded=excluded,
        failed=failed,
        embedded_plain=embedded_plain,
        embedded_ctx=embedded_ctx,
    )


def test_changed_is_true_when_any_bundle_inserted_updated_or_pruned() -> None:
    quiet = _rep("dev", unchanged=5, excluded=1)
    assert not quiet.changed()
    assert not SyncReport(bundles=[quiet, _rep("tax")], seconds=0.1).changed()
    for loud in (
        _rep("tax", inserted=1),
        _rep("tax", updated=1),
        _rep("tax", pruned=1),
    ):
        assert loud.changed()
        assert SyncReport(bundles=[quiet, loud], seconds=0.1).changed()


def test_changed_ignores_failed_excluded_and_embedding_counts() -> None:
    rep = _rep("dev", failed=2, excluded=3, embedded_plain=4, embedded_ctx=4)
    assert not rep.changed()


def test_to_dict_shape_and_values() -> None:
    a = _rep("dev", inserted=2, pruned=1, unchanged=3)
    a.facts = {"explicit": 1}
    a.rebuilt_reason = "changed"
    a.warnings.append("WARN: x type 無し")
    b = _rep("tax", unchanged=4)
    b.skipped_missing_root = True
    d = SyncReport(bundles=[a, b], seconds=1.5).to_dict()
    assert d["changed"] is True
    assert d["seconds"] == 1.5
    assert [x["bundle"] for x in d["bundles"]] == ["dev", "tax"]
    assert d["bundles"][0]["inserted"] == 2
    assert d["bundles"][0]["pruned"] == 1
    assert d["bundles"][0]["facts"] == {"explicit": 1}
    assert d["bundles"][0]["summaries"] is None
    assert d["bundles"][0]["rebuilt_reason"] == "changed"
    assert d["bundles"][1]["rebuilt_reason"] is None
    assert d["bundles"][0]["warnings"] == ["WARN: x type 無し"]
    assert d["bundles"][1]["skipped_missing_root"] is True
    # 辞書は報告の写し（辞書を変えても報告は変わらない）
    d["bundles"][0]["warnings"].append("zzz")
    assert a.warnings == ["WARN: x type 無し"]


def test_run_sync_rejects_unknown_or_unrooted_bundle_before_touching_db(
    tmp_path: Path,
) -> None:
    # DSN は到達不能な値。検査は DB に触れる前なので例外は ValueError のまま
    dsn = "postgresql://nobody@127.0.0.1:1/none"
    with pytest.raises(ValueError, match="語彙外"):
        run_sync(dsn, _FakeNoEmbed(), bundles=["nope"], roots={"dev": tmp_path})
    with pytest.raises(ValueError, match="未指定"):
        run_sync(dsn, _FakeNoEmbed(), bundles=["tax"], roots={"dev": tmp_path})


class _FakeNoEmbed:
    name = "none"
    dims = 384

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        raise AssertionError("呼ばれない")

    def embed_query(self, text: str) -> list[float]:
        raise AssertionError("呼ばれない")
