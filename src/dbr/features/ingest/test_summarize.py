from dbr.features.ingest.summarize import (
    bundle_source_hash,
    doc_source_hash,
    first_paragraph,
    top_headings,
)


def test_top_headings_keeps_order_and_dedupes() -> None:
    chunks = [
        {"heading_path": "A > a1 > deep"},
        {"heading_path": "A > a1"},
        {"heading_path": "B"},
        {"heading_path": ""},
        {"heading_path": "A > a2"},
    ]
    assert top_headings(chunks) == ["A > a1", "B", "A > a2"]


def test_source_hash_is_deterministic_and_order_insensitive() -> None:
    h1 = doc_source_hash({"b": 1, "a": "x"}, ["H1", "H2"])
    h2 = doc_source_hash({"a": "x", "b": 1}, ["H1", "H2"])
    assert h1 == h2 and len(h1) == 64
    assert h1 != doc_source_hash({"a": "x", "b": 1}, ["H1"])  # 見出しが変われば変わる
    assert bundle_source_hash(["- a: x", "- b: y"]) != bundle_source_hash(["- a: x"])


def test_first_paragraph_skips_fences_and_bullets() -> None:
    body = "```\n# not text\ncode\n```\n\n- **要点** は `ここ`。\n- 続き\n\n次の段落\n"
    assert first_paragraph(body) == "要点 は ここ。 続き"


def test_first_paragraph_limit_and_empty() -> None:
    assert first_paragraph("x" * 500, limit=10) == "x" * 10
    assert first_paragraph("") == ""
    assert first_paragraph("```\nonly code\n```") == ""
