"""`dbr ask` の計算本体（F2 型判定 → F3/F4/F5/F6 の配線）.

CLI（単発）・常駐サーバー（`features/serve`）・MCP（`features/mcp_server`）の 3 入口が
**同じ `answer()` を呼ぶ**。既定の計算経路＝測定経路を 1 か所に置くため（CLAUDE.md
「既定・推奨を切り替えたら既定の計算経路を照合する」）。

戻り値は従来 `--json` が出していた dict。テキスト表示は `format_text()` が同じ dict から
組み立てる（常駐経由でも単発でも同じ文面になる）。

exit code の対応: AskError.code = 2 引数不正 / 3 ループバック違反 / 5 モデル・埋め込み不在。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, fields
from typing import Any

from dbr.features.classify import Classification, RuleClassifier
from dbr.features.scope.defaults import DEFAULT_BOOST, DEFAULT_SCOPE
from dbr.shared.db.dsn import LoopbackViolation
from dbr.shared.embed import DEFAULT_MODEL, Embedder, EmbedderUnavailable
from dbr.shared.llm import LLMUnavailable
from dbr.shared.rerank import DEFAULT_RERANKER, Reranker, RerankerUnavailable

ASK_KINDS: tuple[str, ...] = ("auto", "find", "count", "asof", "overview")
# D-17（2026-10-06）: 語彙に当たらない質問は ① 探し物として検索する。判定器（classify）は
# unknown を返し続け、倒すのは ask 層だけ。回答には推定であることを明示する
FALLBACK_REASON = "既知の語彙に当たらない → 探し物として検索（推定）"


class AskError(Exception):
    """利用者に返す失敗。code は CLI の exit code（2 / 3 / 5）."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class AskOptions:
    kind: str = "auto"  # auto | find | count | asof | overview
    mode: str = "embed_ctx"  # D-14（v8）
    agg: str = "rrf_top3"  # D-14（v8）
    rerank_top: int | None = None
    scope: str = DEFAULT_SCOPE  # D-16（v10）
    boost_w: float = DEFAULT_BOOST
    k: int = 5
    model: str = DEFAULT_MODEL
    reranker: str = DEFAULT_RERANKER
    at: str | None = None  # YYYY-MM-DD / YYYY-MM（asof 用）
    llm: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AskOptions:
        """HTTP / MCP から来た dict を検証して作る。未知のキーは exit 2 相当."""
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise AskError(2, f"未知のオプション: {', '.join(unknown)}")
        try:
            return cls(**dict(data))
        except TypeError as exc:
            raise AskError(2, f"オプションの型が不正: {exc}") from exc


def resolve_kind(c: Classification, requested: str) -> tuple[str, bool]:
    """(解決した型, フォールバックしたか)。requested が auto 以外ならそれを採る."""
    if requested != "auto":
        return requested, False
    if c.kind == "unknown":
        return "find", True
    return c.kind, False


def _validate_common(opts: AskOptions) -> Any:
    """型に関係なく先に検査する（--kind bogus が overview に落ちない・--at の書式は
    asof 以外でも exit 2。受入検証 D1）。戻り値は at の datetime（無ければ None）."""
    from dbr.features.asof import parse_at_option
    from dbr.features.scope import SCOPES

    if opts.kind not in ASK_KINDS:
        raise AskError(2, f"--kind は {' | '.join(ASK_KINDS)}")
    if opts.scope not in SCOPES:
        raise AskError(2, f"--scope は {SCOPES} のいずれか")
    at_dt = parse_at_option(opts.at) if opts.at is not None else None
    if opts.at is not None and at_dt is None:
        raise AskError(
            2, "--at は YYYY-MM-DD か YYYY-MM に全体一致（例 2026-08-15 / 2026-08）"
        )
    return at_dt


def answer(
    question: str,
    opts: AskOptions,
    *,
    dsn: str,
    embedder_for: Callable[[str], Embedder],
    reranker_for: Callable[[str], Reranker],
    llm_for: Callable[[str], Any],
) -> dict[str, Any]:
    """型判定 → 該当する道具で答える。

    embedder_for / reranker_for / llm_for は名前 → 実装の供給者。CLI は毎回作り、
    常駐サーバーは 1 回読んだものを返す（モデルの読み込みが応答時間の大半だった）。
    `notes` は stderr に出す注意（WARN）、`warnings` は overview が返す注意。
    """
    from dbr.features.count import VIEWS, ask_view, guess_view
    from dbr.features.scope import boost_by_bundle, guess_bundles
    from dbr.features.search import (
        AGG_CHUNKS,
        AGGS,
        MODES,
        NoEmbeddings,
        aggregate_by_document,
        search,
    )

    at_dt = _validate_common(opts)
    c = RuleClassifier().classify(question)
    resolved, fallback = resolve_kind(c, opts.kind)
    out: dict[str, Any] = {
        "kind": resolved,
        "reason": FALLBACK_REASON if fallback else c.reason,
        "kind_fallback": fallback,
        "notes": [],
    }
    if opts.llm != "none" and resolved != "overview":
        out["notes"].append(
            f"WARN: --llm は overview だけで使う（{resolved} では無視）"
        )

    def _embedder(name: str) -> Embedder:
        try:
            return embedder_for(name)
        except EmbedderUnavailable as exc:
            raise AskError(5, str(exc)) from exc

    def _reranker(name: str) -> Reranker:
        try:
            return reranker_for(name)
        except RerankerUnavailable as exc:
            raise AskError(5, str(exc)) from exc

    try:
        if resolved == "find":
            if opts.mode not in MODES:
                raise AskError(2, f"--mode は {MODES} のいずれか")
            if opts.agg not in AGGS:
                raise AskError(2, f"--agg は {AGGS} のいずれか")
            emb = None if opts.mode == "fts" else _embedder(opts.model)
            rr = _reranker(opts.reranker) if opts.mode.endswith("_rerank") else None
            # 集約 rrf_* は下位断片の和も見るので bench と同じ断片数（AGG_CHUNKS）で
            # 検索する（受入検証 R4(a): 25 断片では測定と順位が食い違った）。max は k*5
            n_chunks = opts.k * 5 if opts.agg == "max" else max(AGG_CHUNKS, opts.k)
            guess = guess_bundles(question) if opts.scope != "none" else None
            try:
                hits = aggregate_by_document(
                    search(
                        question,
                        mode=opts.mode,  # type: ignore[arg-type]
                        dsn=dsn,
                        k=n_chunks,
                        embedder=emb,
                        reranker=rr,
                        rerank_top=opts.rerank_top,
                        bundles=(
                            guess.bundles
                            if (guess and opts.scope == "filter")
                            else None
                        ),
                    ),
                    opts.agg,
                )
            except NoEmbeddings as exc:
                raise AskError(5, str(exc)) from exc
            if guess and opts.scope == "boost":
                hits = boost_by_bundle(hits, guess.bundles, opts.boost_w)
            hits = hits[: opts.k]
            out["mode"] = opts.mode
            out["agg"] = opts.agg
            out["scope"] = opts.scope if guess else None
            out["scope_reason"] = guess.reason if guess else None
            out["hits"] = [
                {
                    "doc": h.doc_key,
                    "heading": h.heading_path,
                    "score": h.score,
                    "source": h.source,
                }
                for h in hits
            ]
            return out
        if resolved == "count":
            view = guess_view(question)
            if view is None:
                raise AskError(
                    2, f"どの集計か決められません。定義済み: {', '.join(sorted(VIEWS))}"
                )
            rows = ask_view(view, dsn)
            out.update({"view": view, "rows": rows})
            return out
        if resolved == "asof":
            from dbr.features.asof import answer_asof

            # ① 探し物で文書を絞ってから時間で絞る。無ければ全文書 → 履歴で補う
            asof_ans = answer_asof(
                question, dsn=dsn, embedder=_embedder(opts.model), at=at_dt, k=opts.k
            )
            at_dt = asof_ans.at
            out["at"] = at_dt.date().isoformat() if at_dt else None
            out["candidate_docs"] = asof_ans.docs
            out["scope"] = asof_ans.scope
            out["n_candidate_chunks"] = len(asof_ans.chunks)
            out["fallback_to_history"] = asof_ans.fallback_to_history
            out["facts"] = [
                {
                    "date": f.valid_from.date().isoformat(),
                    "until": f.valid_to.date().isoformat() if f.valid_to else None,
                    "doc": f.doc_key,
                    "subject": f.subject,
                    "excerpt": f.value[:120],
                    "source": f.valid_source,
                }
                for f in asof_ans.hits
            ]
            return out
        # overview
        from dbr.features.overview import answer as overview_answer
        from dbr.features.overview import narrate

        emb_ov = _embedder(opts.model)
        llm_obj = None
        if opts.llm != "none":
            try:
                llm_obj = llm_for(opts.llm)
            except LLMUnavailable as exc:
                raise AskError(5, str(exc)) from exc
        ov = overview_answer(
            question,
            dsn=dsn,
            embedder=emb_ov,
            scope=opts.scope,
            boost_w=opts.boost_w,
        )
        nar = narrate(question, ov, llm_obj) if llm_obj is not None else None
        out.update(
            {
                "bundles": ov.bundles,
                "bundle_summaries": ov.bundle_summaries,
                "doc_summaries": ov.doc_summaries,
                "evidence_ids": ov.evidence_ids,
                "warnings": ov.warnings,
                "narrative": (
                    {
                        "model": nar.model,
                        "text": nar.text,
                        "unsupported": nar.unsupported,
                        "seconds": nar.seconds,
                    }
                    if nar
                    else None
                ),
            }
        )
        return out
    except LoopbackViolation as exc:
        raise AskError(3, str(exc)) from exc


def format_text(out: Mapping[str, Any]) -> str:
    """`answer()` の dict から stdout の文面を組み立てる（従来の CLI 出力と同じ）."""
    kind = str(out["kind"])
    reason = str(out["reason"])
    lines: list[str] = []
    if kind == "find":
        scope_note = (
            f" / scope={out['scope']}（{out['scope_reason']}）"
            if out.get("scope")
            else ""
        )
        lines.append(
            f"[{kind}] {reason} / mode={out['mode']} / agg={out['agg']}{scope_note}"
        )
        for i, h in enumerate(out["hits"], start=1):
            lines.append(
                f"{i:>2}. {h['doc']}  §{h['heading'] or '-'}  "
                f"({h['source']}, {float(h['score']):.4f})"
            )
        return "\n".join(lines)
    if kind == "count":
        lines.append(f"[{kind}] {reason} / 定義={out['view']}")
        for r in out["rows"]:
            lines.append("  " + "  ".join(f"{k2}={v}" for k2, v in r.items()))
        return "\n".join(lines)
    if kind == "asof":
        at = out.get("at")
        head = f"時点 {at} の事実" if at else "履歴（関連度順）"
        if out.get("fallback_to_history"):
            head += "（その時点の記録なし → 関連する記録を履歴から・関連度順）"
        sc = out.get("scope")
        if sc == "chunks":
            scope = f"断片を絞った（質問に近い {out['n_candidate_chunks']} 断片）"
        elif sc == "docs":
            scope = f"文書を絞った: {', '.join(out['candidate_docs'])}"
        else:
            scope = "全文書"
        lines.append(f"[{kind}] {reason} / {head} / {scope}")
        facts = out["facts"]
        if not facts:
            lines.append("  該当する記録なし")
        for f in facts:
            until = f" 〜 {f['until']}" if f.get("until") else ""
            flag = "（暫定）" if f["source"] == "inferred" else ""
            lines.append(
                f"  {f['date']}{until}{flag}  {f['doc']}\n      {f['excerpt']}"
            )
        return "\n".join(lines)
    # overview
    lines.append(f"[{kind}] {reason} / 対象 bundle: {', '.join(out['bundles'])}")
    for b in out["bundle_summaries"]:
        lines.append(f"\n■ {b['bundle']}（summary#{b['id']}）\n{b['text']}")
    if out["doc_summaries"]:
        lines.append("\n■ 質問に近い文書（上位）")
        for d in out["doc_summaries"]:
            lines.append(
                f"- [{d['doc']}]（summary#{d['id']}）\n  "
                + str(d["text"]).replace("\n", "\n  ")
            )
    nar = out.get("narrative")
    if nar:
        lines.append(
            f"\n■ LLM の回答（{nar['model']}・{nar['seconds']} 秒）\n{nar['text']}"
        )
        lines.append("根拠外の言及: " + (", ".join(nar["unsupported"]) or "なし"))
    return "\n".join(lines)


def stderr_notes(out: Mapping[str, Any]) -> list[str]:
    """stderr に出す行（CLI の WARN と overview の warnings）."""
    notes = [str(n) for n in out.get("notes", [])]
    notes.extend(f"WARN: {w}" for w in out.get("warnings", []) or [])
    return notes


__all__ = [
    "ASK_KINDS",
    "FALLBACK_REASON",
    "AskError",
    "AskOptions",
    "answer",
    "format_text",
    "resolve_kind",
    "stderr_notes",
]
