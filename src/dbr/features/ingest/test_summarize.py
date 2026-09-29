from dbr.features.ingest.summarize import first_paragraph


def test_first_paragraph_skips_fences_and_bullets() -> None:
    body = "```\n# not text\ncode\n```\n\n- **要点** は `ここ`。\n- 続き\n\n次の段落\n"
    assert first_paragraph(body) == "要点 は ここ。 続き"


def test_first_paragraph_limit_and_empty() -> None:
    assert first_paragraph("x" * 500, limit=10) == "x" * 10
    assert first_paragraph("") == ""
    assert first_paragraph("```\nonly code\n```") == ""
