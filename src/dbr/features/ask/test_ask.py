"""ask 層のユニット（DB 不要）: フォールバック・検査順序・オプションの受け渡し・文面."""

from __future__ import annotations

import pytest

from dbr.features.ask import (
    FALLBACK_REASON,
    AskError,
    AskOptions,
    answer,
    format_text,
    resolve_kind,
    stderr_notes,
)
from dbr.features.classify import Classification, RuleClassifier


def _fail(_name: str) -> object:
    raise AssertionError("ここに来るなら検査順序が壊れている")


def test_fallback_only_when_auto_and_unknown() -> None:
    unknown = Classification("unknown", "既知の語彙に当たらない", 0.0)
    assert resolve_kind(unknown, "auto") == ("find", True)
    assert resolve_kind(unknown, "count") == ("count", False)
    found = Classification("count", "件数を問う語「何件」", 0.9)
    assert resolve_kind(found, "auto") == ("count", False)
    assert resolve_kind(found, "overview") == ("overview", False)


def test_classifier_itself_still_returns_unknown() -> None:
    # D-17: 倒すのは ask 層。判定器は正直なまま
    c = RuleClassifier().classify("Codex の起動で PATH の罠は何だった？")
    assert c.kind == "unknown"


@pytest.mark.parametrize(
    ("opts", "fragment"),
    [
        (AskOptions(kind="bogus"), "--kind"),
        (AskOptions(scope="nope"), "--scope"),
        (AskOptions(at="2026-13"), "--at"),
        (AskOptions(kind="find", mode="nope"), "--mode"),
        (AskOptions(kind="find", agg="mean"), "--agg"),
    ],
)
def test_option_errors_are_exit_2_before_any_model_load(
    opts: AskOptions, fragment: str
) -> None:
    with pytest.raises(AskError) as ei:
        answer(
            "何件？",
            opts,
            dsn="postgresql://x@127.0.0.1/none",
            embedder_for=_fail,  # type: ignore[arg-type]
            reranker_for=_fail,  # type: ignore[arg-type]
            llm_for=_fail,
        )
    assert ei.value.code == 2 and fragment in str(ei.value)


def test_from_dict_rejects_unknown_keys_and_roundtrips() -> None:
    o = AskOptions(kind="find", k=3, at="2026-08")
    assert AskOptions.from_dict(o.to_dict()) == o
    with pytest.raises(AskError) as ei:
        AskOptions.from_dict({"kind": "find", "foo": 1})
    assert ei.value.code == 2 and "foo" in str(ei.value)


def test_format_text_find_marks_fallback_reason() -> None:
    out = {
        "kind": "find",
        "reason": FALLBACK_REASON,
        "kind_fallback": True,
        "notes": [],
        "mode": "embed_ctx",
        "agg": "rrf_top3",
        "scope": None,
        "scope_reason": None,
        "hits": [
            {"doc": "dev/a.md", "heading": "x > y", "score": 0.5, "source": "embed"}
        ],
    }
    text = format_text(out)
    assert text.splitlines()[0] == (
        f"[find] {FALLBACK_REASON} / mode=embed_ctx / agg=rrf_top3"
    )
    assert " 1. dev/a.md  §x > y  (embed, 0.5000)" in text


def test_stderr_notes_merges_cli_warn_and_overview_warnings() -> None:
    out = {"notes": ["WARN: a"], "warnings": ["b"]}
    assert stderr_notes(out) == ["WARN: a", "WARN: b"]
