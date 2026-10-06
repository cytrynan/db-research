"""`dbr sync`: 正本フォルダの 変更・新規・削除 を DB に反映する（差分・冪等）.

bundle ごとに ingest → prune → embed(plain/ctx) →（変更 or 要約の陳腐化があれば）
facts → summarize。
正本は Markdown、DB は派生（D-9）。「正本にある」は ingest と同じ関数で決める
（iter_markdown → normalize_rel_path → is_excluded）ので、`private.md` などの除外は
取り込みと削除で食い違わない。
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from dbr.features.ingest.embed import run_embed
from dbr.features.ingest.facts import run_facts
from dbr.features.ingest.handler import (
    BUNDLES,
    is_excluded,
    iter_markdown,
    normalize_rel_path,
)
from dbr.features.ingest.handler import run as run_ingest
from dbr.features.ingest.summarize import run_summarize, stale_summaries
from dbr.shared.db import connect
from dbr.shared.embed import Embedder

# 同期の順序（台帳）。ingest.BUNDLES は集合なので、順序つきの一覧をここで 1 か所に持つ
BUNDLES_ORDER: tuple[str, ...] = (
    "references",
    "dev",
    "memory",
    "stock",
    "tax",
    "scout",
    "experiments",
)
ENV_ROOT_PREFIX = "DBR_ROOT_"


def bundle_roots() -> dict[str, Path]:
    """bundle → 正本フォルダ。環境変数 `DBR_ROOT_<BUNDLE 大文字>` があれば上書き.

    存在しないフォルダも dict には入れる（走らせるか skip するかは呼び手が決める）。
    """
    home = Path.home()
    knowledge = home / ".agents" / "knowledge"
    roots: dict[str, Path] = {
        "references": home / ".claude" / "references",
        "memory": home / ".claude" / "projects" / "C--Users-meer0" / "memory",
    }
    for bundle in ("dev", "stock", "tax", "scout", "experiments"):
        roots[bundle] = knowledge / bundle
    for bundle in BUNDLES_ORDER:
        override = os.environ.get(f"{ENV_ROOT_PREFIX}{bundle.upper()}")
        if override:
            roots[bundle] = Path(override).expanduser()
    return {bundle: roots[bundle] for bundle in BUNDLES_ORDER}


@dataclass
class BundleSyncReport:
    bundle: str
    root: str
    skipped_missing_root: bool = False
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    excluded: int = 0
    failed: int = 0
    pruned: int = 0  # 正本から消えたので DB から削除した document 数
    embedded_plain: int = 0
    embedded_ctx: int = 0
    facts: dict[str, int] | None = (
        None  # run_facts の to_dict（変更があった bundle だけ）
    )
    summaries: dict[str, int] | None = None  # run_summarize の to_dict（同上）
    # facts / summarize を作り直した理由。"changed"（取り込み・削除があった）/
    # "stale_summaries"（変更は無いが要約が欠けている・古い＝途中で落ちた跡）/ None
    rebuilt_reason: str | None = None
    seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def changed(self) -> bool:
        return (self.inserted + self.updated + self.pruned) > 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SyncReport:
    bundles: list[BundleSyncReport]
    seconds: float

    def changed(self) -> bool:
        """どれかの bundle に inserted / updated / pruned があったか."""
        return any(b.changed() for b in self.bundles)

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed(),
            "seconds": self.seconds,
            "bundles": [b.to_dict() for b in self.bundles],
        }


def prune(dsn: str, bundle: str, root: Path) -> int:
    """DB にあって正本に無い document を削除して件数を返す.

    document の削除で chunk / chunk_embedding / fact は FK CASCADE で消える。summary は
    FK を持たない（target_key は id の文字列）ので同じトランザクションで自分で消す:
    level='document' は document.id、level='section' はその文書の chunk.id。
    bundle 階層の要約は run_summarize が作り直す。

    root が存在しないときは例外にする（外付け・未マウントで空に見えたフォルダを
    「全部消えた」と読んで DB を空にする事故を防ぐ。呼び手の run_sync は先に skip する）。
    """
    if bundle not in BUNDLES:
        raise ValueError(f"bundle が語彙外: {bundle!r}（{sorted(BUNDLES)}）")
    if not root.is_dir():
        raise ValueError(f"正本フォルダが存在しません（削除の反映を中止）: {root}")
    alive: set[str] = set()
    for path in iter_markdown(root):
        rel = normalize_rel_path(root, path)
        if not is_excluded(rel):
            alive.add(rel)
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, rel_path FROM document WHERE bundle = %(b)s", {"b": bundle}
        )
        gone = [
            int(str(r["id"])) for r in cur.fetchall() if str(r["rel_path"]) not in alive
        ]
        if not gone:
            return 0
        cur.execute(
            "DELETE FROM summary WHERE (level = 'document' "
            "  AND target_key = ANY(%(ids)s::text[])) "
            "OR (level = 'section' AND target_key IN "
            "   (SELECT id::text FROM chunk "
            "    WHERE document_id = ANY(%(idn)s::bigint[])))",
            {"ids": [str(i) for i in gone], "idn": gone},
        )
        cur.execute(
            "DELETE FROM document WHERE id = ANY(%(idn)s::bigint[])", {"idn": gone}
        )
        return cur.rowcount


def summaries_stale(dsn: str, bundle: str) -> bool:
    """bundle の要約が欠けている・古いか（取り込み後に落ちた跡を次回の sync で拾う）.

    bundle 階層の要約行が無い、または `stale_summaries`（source_hash を要約時と同じ
    関数で再計算して突き合わせる）が 1 件でもあれば True。
    """
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM summary "
            "WHERE level = 'bundle' AND target_key = %(b)s",
            {"b": bundle},
        )
        row = cur.fetchone()
    if row is None or int(str(row["n"])) == 0:
        return True
    return len(stale_summaries(dsn, [bundle])) > 0


def run_sync(
    dsn: str,
    embedder: Embedder,
    *,
    bundles: Sequence[str] | None = None,
    roots: Mapping[str, Path] | None = None,
    log: Callable[[str], None] = print,
) -> SyncReport:
    """bundle ごとに ingest → prune → embed(plain, ctx) →（変更 or 要約の陳腐化）facts → summarize.

    - `roots` 省略時は bundle_roots()。渡したときはその dict だけが対象（無い bundle は
      既定のフォルダへ逃げない＝テストが実データに触れない）。`bundles` 省略時は
      対象の dict にある bundle を BUNDLES_ORDER の順に処理する
    - root が存在しなければ skipped_missing_root=True で次へ（例外にしない）
    - PersonalDataRejected（境界違反）は握らずそのまま投げる（全体停止＝既存方針）
    - 「変更があった」= inserted + updated + pruned > 0 → rebuilt_reason="changed"。
      無変更でも summaries_stale()（要約が欠けている・古い）なら作り直す
      （"stale_summaries"。ingest の後・facts/summarize の前に落ちた跡を拾う）。
      どちらでもなければ走らせない（件数の確認と埋め込みの未生成分チェックだけ）
    - log は 1 bundle 1 行（件数だけ。本文・ファイル名は出さない）
    """
    started = time.perf_counter()
    targets = dict(roots) if roots is not None else bundle_roots()
    wanted = list(bundles) if bundles is not None else list(targets)
    for b in wanted:
        if b not in BUNDLES:
            raise ValueError(f"bundle が語彙外: {b!r}（{sorted(BUNDLES)}）")
        if b not in targets:
            raise ValueError(f"bundle {b!r} の正本フォルダが未指定（roots に無い）")
    reports: list[BundleSyncReport] = []
    for bundle in (b for b in BUNDLES_ORDER if b in wanted):
        root = targets[bundle]
        t0 = time.perf_counter()
        rep = BundleSyncReport(bundle=bundle, root=str(root))
        if not root.is_dir():
            rep.skipped_missing_root = True
            rep.warnings.append("WARN: 正本フォルダが無いので skip")
            log(f"sync {bundle}: skip（正本フォルダが無い）")
            reports.append(rep)
            continue
        ing = run_ingest(root, bundle, dsn, log=log)
        rep.inserted = ing.inserted
        rep.updated = ing.updated
        rep.unchanged = ing.skipped
        rep.excluded = ing.excluded
        rep.failed = ing.failed
        rep.warnings.extend(ing.warnings)
        rep.pruned = prune(dsn, bundle, root)
        # 未生成分だけ計算する冪等実装なので、変更の有無に関わらず毎回呼ぶ
        rep.embedded_plain = run_embed(bundle, "plain", dsn, embedder).computed
        rep.embedded_ctx = run_embed(bundle, "ctx", dsn, embedder).computed
        if rep.changed():
            rep.rebuilt_reason = "changed"
        elif summaries_stale(dsn, bundle):
            rep.rebuilt_reason = "stale_summaries"
        if rep.rebuilt_reason is not None:
            rep.facts = run_facts(bundle, dsn).to_dict()
            rep.summaries = run_summarize(bundle, dsn).to_dict()
        rep.seconds = time.perf_counter() - t0
        log(
            f"sync {bundle}: 追加 {rep.inserted} / 更新 {rep.updated} / "
            f"削除 {rep.pruned} / 変更なし {rep.unchanged} / 除外 {rep.excluded} / "
            f"失敗 {rep.failed} / 埋め込み plain {rep.embedded_plain} "
            f"ctx {rep.embedded_ctx} / 要約の再構築 {rep.rebuilt_reason or 'なし'} / "
            f"{rep.seconds:.1f}s"
        )
        reports.append(rep)
    return SyncReport(bundles=reports, seconds=time.perf_counter() - started)
