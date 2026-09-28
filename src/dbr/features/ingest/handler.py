"""フォルダ走査 → document / chunk への挿入（冪等・境界つき）.

- `private.md` と `*.bak*` は走査で除外し、DB 側トリガーが二重に拒否する
- `content_hash` が一致する既存行は skip（再実行で行数が増えない）
- 境界違反（トリガー拒否）は rollback して全体を止める
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from dbr.features.ingest.chunker import split
from dbr.features.ingest.context import context_for
from dbr.features.ingest.frontmatter import FrontmatterError, ParsedDoc, parse
from dbr.shared.db import connect

BUNDLES = frozenset(
    {"references", "dev", "stock", "tax", "scout", "memory", "experiments"}
)
PRIVATE_NAME = "private.md"


class PersonalDataRejected(Exception):
    """DB 側の境界（private.md トリガー）に当たった。全体を停止する."""

    def __init__(self, rel_path: str) -> None:
        self.rel_path = rel_path
        super().__init__(f"拒否: 境界違反 ({rel_path})。取り込みを停止しました")


@dataclass
class IngestReport:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    excluded: int = 0
    rejected: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "failed": self.failed,
            "excluded": self.excluded,
            "rejected": self.rejected,
            "warnings": list(self.warnings),
        }


def normalize_rel_path(root: Path, path: Path) -> str:
    """POSIX 区切り・NFC・先頭 './' 無し。書き側と読み側で同じ関数を使う."""
    rel = path.relative_to(root).as_posix()
    rel = unicodedata.normalize("NFC", rel)
    return rel.removeprefix("./")


def is_excluded(rel_path: str) -> bool:
    # 大文字小文字は区別しない（Windows の FS は区別せず `Private.md` が同一ファイル）
    name = rel_path.rsplit("/", 1)[-1].lower()
    if name == PRIVATE_NAME or name.startswith(PRIVATE_NAME + "."):
        return True
    return ".bak" in name


def iter_markdown(root: Path) -> Iterator[Path]:
    for p in sorted(root.rglob("*.md")):
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        yield p


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _jsonb(obj: dict[str, Any]) -> Jsonb:
    return Jsonb(obj, dumps=lambda o: json.dumps(o, ensure_ascii=False, default=str))


def _upsert(
    conn: psycopg.Connection[dict[str, object]],
    *,
    bundle: str,
    rel_path: str,
    doc: ParsedDoc,
    digest: str,
    existing_id: int | None,
) -> int:
    params: dict[str, Any] = {
        "bundle": bundle,
        "rel_path": rel_path,
        "format": doc.format,
        "fm": _jsonb(doc.fm),
        "type": doc.type,
        "status": doc.status,
        "generated_at": doc.generated_at,
        "verified_at": doc.verified_at,
        "stale_after": doc.stale_after,
        "content_hash": digest,
    }
    with conn.cursor() as cur:
        if existing_id is None:
            cur.execute(
                """
                INSERT INTO document
                    (bundle, rel_path, format, fm, type, status,
                     generated_at, verified_at, stale_after, content_hash)
                VALUES
                    (%(bundle)s, %(rel_path)s, %(format)s, %(fm)s, %(type)s,
                     %(status)s, %(generated_at)s, %(verified_at)s,
                     %(stale_after)s, %(content_hash)s)
                RETURNING id
                """,
                params,
            )
            row = cur.fetchone()
            assert row is not None
            doc_id = int(str(row["id"]))
        else:
            params["id"] = existing_id
            cur.execute(
                """
                UPDATE document SET
                    format=%(format)s, fm=%(fm)s, type=%(type)s, status=%(status)s,
                    generated_at=%(generated_at)s, verified_at=%(verified_at)s,
                    stale_after=%(stale_after)s, content_hash=%(content_hash)s,
                    ingested_at=now()
                WHERE id=%(id)s
                """,
                params,
            )
            cur.execute(
                "DELETE FROM chunk WHERE document_id=%(id)s", {"id": existing_id}
            )
            doc_id = existing_id

        description = doc.fm.get("description")
        desc = str(description) if isinstance(description, str) else None
        # 断片は COPY で一括投入する（1ファイル数十断片。往復を1回にする）。
        # ※ 2026-09-29 の「取り込み 2 分」は INSERT ではなく localhost→::1 の接続待ちが
        #   原因だった（shared/db.connect のコメント参照）。INSERT 自体は速い。
        with cur.copy(
            "COPY chunk (document_id, ordinal, heading_path, body, context, tokens) "
            "FROM STDIN"
        ) as copy:
            for c in split(doc.body):
                copy.write_row(
                    (
                        doc_id,
                        c.ordinal,
                        c.heading_path,
                        c.body,
                        context_for(bundle, rel_path, c.heading_path, desc),
                        c.tokens,
                    )
                )
    return doc_id


def run(
    root: Path,
    bundle: str,
    dsn: str,
    *,
    log: Callable[[str], None] = print,
) -> IngestReport:
    """root 配下の .md を bundle として取り込む。戻り値は件数の内訳."""
    if bundle not in BUNDLES:
        raise ValueError(f"bundle が語彙外: {bundle!r}（{sorted(BUNDLES)}）")
    report = IngestReport()
    conn = connect(dsn)  # ループバック検査はここ（接続前）
    with conn:
        for path in iter_markdown(root):
            rel = normalize_rel_path(root, path)
            if is_excluded(rel):
                report.excluded += 1
                continue
            text = path.read_text(encoding="utf-8-sig")
            try:
                doc = parse(text, rel)
            except FrontmatterError as exc:
                report.failed += 1
                report.warnings.append(f"WARN: {rel} フロントマター不正 ({exc.reason})")
                continue
            digest = content_hash(text)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, content_hash FROM document "
                    "WHERE bundle=%(b)s AND rel_path=%(r)s",
                    {"b": bundle, "r": rel},
                )
                existing = cur.fetchone()
            if existing is not None and existing["content_hash"] == digest:
                report.skipped += 1
                continue
            existing_id = int(str(existing["id"])) if existing is not None else None
            try:
                with conn.transaction():
                    _upsert(
                        conn,
                        bundle=bundle,
                        rel_path=rel,
                        doc=doc,
                        digest=digest,
                        existing_id=existing_id,
                    )
            except psycopg.errors.CheckViolation as exc:
                report.rejected += 1
                log(f"拒否: {rel}")
                raise PersonalDataRejected(rel) from exc
            if existing_id is None:
                report.inserted += 1
            else:
                report.updated += 1
            if doc.type is None:
                report.warnings.append(f"WARN: {rel} type 無し")
    return report
