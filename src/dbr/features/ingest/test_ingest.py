"""取り込みのユニット（DB 不要）: frontmatter 6ケース・chunker・正規化・除外."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from dbr.features.ingest.chunker import split
from dbr.features.ingest.frontmatter import JST, FrontmatterError, parse
from dbr.features.ingest.handler import is_excluded, normalize_rel_path

# ---- frontmatter ----------------------------------------------------------


def test_parse_plain_okf_is_okf_format() -> None:
    doc = parse(
        "---\ntype: Note\n"
        "generated: { by: x/y, at: 2026-09-01T10:00:00+09:00 }\n---\n# a\n"
    )
    assert doc.format == "okf"
    assert doc.type == "Note"
    assert doc.status == "stable"
    assert doc.generated_at == datetime(2026, 9, 1, 10, tzinfo=JST)
    assert doc.verified_at is None


def test_parse_kuroko_extension_by_description_and_vocab() -> None:
    doc = parse(
        "---\ntype: Tech Note\ndescription: x\n"
        "updated: { by: a/b, at: 2026-09-26 }\n---\nbody"
    )
    assert doc.format == "kuroko"
    assert doc.fm["updated"]  # 規約外キーも fm には残る


def test_parse_memory_nested_metadata() -> None:
    text = (
        "---\nname: m\ndescription: x\nmetadata:\n  type: feedback\n"
        "  generated:\n    by: kuroko/pre-okf\n    at: 2026-07-18T15:21:46.156Z\n"
        "  verified:\n    by: human:K\n---\n# m\n"
    )
    doc = parse(text)
    assert doc.format == "kuroko"
    assert doc.type == "feedback"
    assert doc.generated_at == datetime(2026, 7, 18, 15, 21, 46, 156000, tzinfo=UTC)
    assert doc.verified_at is None  # at が無い verified は None


def test_parse_date_only_at_becomes_jst_midnight() -> None:
    doc = parse(
        "---\ntype: Note\ngenerated: { by: x, at: 2026-09-28 }\n"
        "stale_after: 2027-04-01\n---\n"
    )
    assert doc.generated_at == datetime(2026, 9, 28, 0, 0, tzinfo=JST)
    assert doc.stale_after == date(2027, 4, 1)


def test_parse_verified_list_takes_latest() -> None:
    text = (
        "---\ntype: Note\nverified:\n"
        "  - { by: human:K, at: 2026-08-01T00:00:00+09:00 }\n"
        "  - { by: human:K, at: 2026-09-01T00:00:00+09:00 }\n---\n"
    )
    assert parse(text).verified_at == datetime(2026, 9, 1, tzinfo=JST)


def test_parse_no_frontmatter_and_no_type() -> None:
    doc = parse("# just body\n\ntext")
    assert doc.type is None
    assert doc.format == "okf"
    assert doc.body.startswith("# just body")


def test_parse_broken_yaml_raises() -> None:
    with pytest.raises(FrontmatterError) as ei:
        parse("---\ntype: [unclosed\n---\nbody", rel_path="x.md")
    assert ei.value.rel_path == "x.md"


# ---- chunker --------------------------------------------------------------


def test_split_by_headings_with_path() -> None:
    md = "intro\n\n# A\n\na1\n\n## B\n\nb1\n\n### C\n\nc1\n\n## D\n\nd1\n"
    chunks = split(md)
    assert [c.heading_path for c in chunks] == ["", "A", "A > B", "A > B > C", "A > D"]
    assert [c.ordinal for c in chunks] == [0, 1, 2, 3, 4]


def test_split_ignores_hash_inside_code_fence() -> None:
    md = "# A\n\n```\n# not a heading\n```\n\ntext"
    chunks = split(md)
    assert len(chunks) == 1
    assert "# not a heading" in chunks[0].body


def test_split_long_section_at_paragraphs() -> None:
    para = "x" * 600
    md = "# A\n\n" + "\n\n".join([para] * 4)  # 約1200 トークン相当
    chunks = split(md, max_tokens=800)
    assert len(chunks) >= 2
    assert all(c.heading_path == "A" for c in chunks)
    assert all(c.tokens <= 800 for c in chunks)


# ---- path rules -----------------------------------------------------------


def test_normalize_rel_path_posix_nfc(tmp_path: Path) -> None:
    p = tmp_path / "sub" / "ファイル.md"
    p.parent.mkdir()
    p.write_text("x", encoding="utf-8")
    assert normalize_rel_path(tmp_path, p) == "sub/ファイル.md"


@pytest.mark.parametrize(
    "rel,excluded",
    [
        ("private.md", True),
        ("deep/private.md", True),
        ("private.md.bak-20260811", True),
        ("notes.bak.md", True),
        ("privateer.md", False),
        ("a/b.md", False),
    ],
)
def test_is_excluded(rel: str, excluded: bool) -> None:
    assert is_excluded(rel) is excluded
