"""CLI `dbr`。配線だけを書き、ロジックはスライス側に置く.

exit code: 0 正常 / 1 その他 / 2 未定義の集計 / 3 ループバック違反 /
4 境界違反 (private.md 等)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from dbr.shared.db import LoopbackViolation, connect, resolve_dsn
from dbr.shared.db.migrate import migrate as run_migrations

app = typer.Typer(no_args_is_help=True, add_completion=False)

# Windows の既定コンソール（cp932）は「—」等で UnicodeEncodeError になり
# JSON 出力が落ちる（2026-09-29 実測）。標準出力・エラーを UTF-8 に固定する
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

DsnOpt = Annotated[
    str | None, typer.Option("--dsn", help="接続文字列。省略時は環境変数 DBR_DSN")
]
JsonOpt = Annotated[bool, typer.Option("--json", help="JSON だけを出力")]


@app.callback()
def _root() -> None:
    """質問の型で振り分ける個人記録の検索基盤 (研究用)."""
    # サブコマンドが1つでも「dbr <subcommand>」の形を保つための callback


def _exit_on_loopback(exc: LoopbackViolation) -> typer.Exit:
    typer.echo(str(exc), err=True)
    return typer.Exit(code=3)


@app.command()
def migrate(dsn: DsnOpt = None, as_json: JsonOpt = False) -> None:
    """migrations/ を番号順に適用する (適用済みは飛ばす)."""
    try:
        conn = connect(resolve_dsn(dsn))
    except LoopbackViolation as exc:
        raise _exit_on_loopback(exc) from None
    with conn:
        applied = run_migrations(conn, MIGRATIONS_DIR)
    if as_json:
        typer.echo(json.dumps({"applied": applied}, ensure_ascii=False))
    else:
        detail = ": " + ", ".join(applied) if applied else ""
        typer.echo(f"適用 {len(applied)} 件{detail}")


@app.command()
def ingest(
    root: Annotated[
        Path, typer.Argument(exists=True, file_okay=False, resolve_path=True)
    ],
    bundle: Annotated[str, typer.Option("--bundle", help="references/dev/stock/…")],
    dsn: DsnOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """OKF フォルダを document/chunk へ取り込む（冪等・localhost 限定）."""
    from dbr.features.ingest import BUNDLES, PersonalDataRejected, run

    if bundle not in BUNDLES:
        typer.echo(f"--bundle は {sorted(BUNDLES)} のいずれか", err=True)
        raise typer.Exit(code=2)
    try:
        report = run(
            root, bundle, resolve_dsn(dsn), log=lambda m: typer.echo(m, err=True)
        )
    except LoopbackViolation as exc:
        raise _exit_on_loopback(exc) from None
    except PersonalDataRejected as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=4) from None
    if as_json:
        typer.echo(json.dumps(report.to_dict(), ensure_ascii=False))
        return
    d = report.to_dict()
    typer.echo(
        f"新規 {d['inserted']} / 更新 {d['updated']} / skip {d['skipped']} / "
        f"失敗 {d['failed']} / 除外 {d['excluded']} / 拒否 {d['rejected']}"
    )
    for w in report.warnings:
        typer.echo(w, err=True)


@app.command()
def count(
    view: Annotated[
        str, typer.Argument(help="v_by_bundle / v_by_type / v_unverified / v_stale")
    ],
    dsn: DsnOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """② 数える: 定義済みビューの結果を返す（毎回同じ定義＝同じ数字）."""
    from dbr.features.count import UnknownAggregate, ask_view

    try:
        rows = ask_view(view, resolve_dsn(dsn))
    except UnknownAggregate as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from None
    except LoopbackViolation as exc:
        raise _exit_on_loopback(exc) from None
    if as_json:
        typer.echo(
            json.dumps({"view": view, "rows": rows}, ensure_ascii=False, default=str)
        )
        return
    typer.echo(f"定義: {view}")
    for r in rows:
        typer.echo("  " + "  ".join(f"{k}={v}" for k, v in r.items()))


@app.command()
def embed(
    bundle: Annotated[str, typer.Option("--bundle")],
    variant: Annotated[str, typer.Option("--variant", help="plain | ctx")] = "plain",
    model: Annotated[str, typer.Option("--model")] = "intfloat/multilingual-e5-small",
    dsn: DsnOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """未生成の断片だけ埋め込みを計算して保存する（冪等・ローカルモデルのみ）."""
    from dbr.features.ingest import BUNDLES
    from dbr.features.ingest.embed import run_embed
    from dbr.shared.embed import EmbedderUnavailable, get_embedder

    if bundle not in BUNDLES or variant not in {"plain", "ctx"}:
        typer.echo("--bundle は語彙内、--variant は plain|ctx", err=True)
        raise typer.Exit(code=2)
    try:
        embedder = get_embedder(model)
        report = run_embed(bundle, variant, resolve_dsn(dsn), embedder)  # type: ignore[arg-type]
    except EmbedderUnavailable as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=5) from None
    except LoopbackViolation as exc:
        raise _exit_on_loopback(exc) from None
    if as_json:
        typer.echo(json.dumps(report.to_dict(), ensure_ascii=False))
    else:
        typer.echo(
            f"計算 {report.computed} / 既存 {report.skipped_existing}"
            f"（{report.model} / {report.variant}）"
        )


@app.command()
def classify(
    question: Annotated[str, typer.Argument()], as_json: JsonOpt = False
) -> None:
    """質問の型（find / count / asof / overview / unknown）と理由を返す."""
    from dbr.features.classify import RuleClassifier

    r = RuleClassifier().classify(question)
    if as_json:
        typer.echo(json.dumps(r.__dict__, ensure_ascii=False))
    else:
        typer.echo(f"{r.kind}  ({r.reason}, confidence={r.confidence})")


REPO_ROOT = Path(__file__).resolve().parents[2]


def _embedder_or_exit(model: str) -> Any:
    from dbr.shared.embed import EmbedderUnavailable, get_embedder

    try:
        return get_embedder(model)
    except EmbedderUnavailable as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=5) from None


def _reranker_or_exit(name: str) -> Any:
    from dbr.shared.rerank import RerankerUnavailable, get_reranker

    try:
        return get_reranker(name)
    except RerankerUnavailable as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=5) from None


RerankerOpt = Annotated[
    str, typer.Option("--reranker", help="cross-encoder のモデル名（fake で配線確認）")
]
DEFAULT_RERANKER_NAME = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
LlmOpt = Annotated[
    str,
    typer.Option("--llm", help="overview: ローカル LLM 名 | fake | none（既定 none）"),
]


def _llm_or_exit(name: str) -> Any:
    from dbr.shared.llm import LLMUnavailable, get_llm

    try:
        return get_llm(name)
    except LLMUnavailable as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=5) from None


ASK_KINDS = ("auto", "find", "count", "asof", "overview")


@app.command()
def ask(
    question: Annotated[str, typer.Argument()],
    mode: Annotated[str, typer.Option("--mode")] = "embed_ctx",  # D-14（v8）
    agg: Annotated[
        str, typer.Option("--agg", help="find の文書集約 max | rrf_all | rrf_top3")
    ] = "rrf_top3",  # D-14（v8）
    rerank_top: Annotated[
        int | None,
        typer.Option("--rerank-top", help="並べ直す候補数。省略でモード別既定"),
    ] = None,
    kind: Annotated[
        str, typer.Option("--kind", help="auto | find | count | asof | overview")
    ] = "auto",
    k: Annotated[int, typer.Option("--k")] = 5,
    model: Annotated[str, typer.Option("--model")] = "intfloat/multilingual-e5-small",
    reranker: RerankerOpt = DEFAULT_RERANKER_NAME,
    at: Annotated[
        str | None, typer.Option("--at", help="時点（YYYY-MM-DD / YYYY-MM）。asof 用")
    ] = None,
    llm: LlmOpt = "none",
    dsn: DsnOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """型判定 → 該当する道具で答える（find / count / asof / overview）."""
    from dbr.features.asof import parse_at_option
    from dbr.features.classify import RuleClassifier
    from dbr.features.count import VIEWS, ask_view
    from dbr.features.search import (
        AGG_CHUNKS,
        AGGS,
        MODES,
        NoEmbeddings,
        aggregate_by_document,
        search,
    )

    # オプションの検査は型に関係なく先にやる（--kind bogus が overview に落ちない・
    # --at の書式は asof 以外でも exit 2。受入検証 D1）
    if kind not in ASK_KINDS:
        typer.echo(f"--kind は {' | '.join(ASK_KINDS)}", err=True)
        raise typer.Exit(code=2)
    at_dt = parse_at_option(at) if at is not None else None
    if at is not None and at_dt is None:
        typer.echo(
            "--at は YYYY-MM-DD か YYYY-MM に全体一致（例 2026-08-15 / 2026-08）",
            err=True,
        )
        raise typer.Exit(code=2)
    c = RuleClassifier().classify(question)
    resolved = c.kind if kind == "auto" else kind
    out: dict[str, Any] = {"kind": resolved, "reason": c.reason}
    if resolved == "unknown":
        typer.echo(
            "型を判定できません。--kind find か --kind count を指定してください",
            err=True,
        )
        raise typer.Exit(code=2)
    if resolved == "find":
        if mode not in MODES:
            typer.echo(f"--mode は {MODES} のいずれか", err=True)
            raise typer.Exit(code=2)
        if agg not in AGGS:
            typer.echo(f"--agg は {AGGS} のいずれか", err=True)
            raise typer.Exit(code=2)
        emb = None if mode == "fts" else _embedder_or_exit(model)
        rr = _reranker_or_exit(reranker) if mode.endswith("_rerank") else None
        # 集約 rrf_* は下位断片の和も見るので bench と同じ断片数（AGG_CHUNKS）で
        # 検索する（受入検証 R4(a): 25 断片では測定と順位が食い違った）。max は k*5
        n_chunks = k * 5 if agg == "max" else max(AGG_CHUNKS, k)
        try:
            hits = aggregate_by_document(
                search(
                    question,
                    mode=mode,  # type: ignore[arg-type]
                    dsn=resolve_dsn(dsn),
                    k=n_chunks,
                    embedder=emb,
                    reranker=rr,
                    rerank_top=rerank_top,
                ),
                agg,
            )[:k]
        except NoEmbeddings as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=5) from None
        except LoopbackViolation as exc:
            raise _exit_on_loopback(exc) from None
        out["hits"] = [
            {
                "doc": h.doc_key,
                "heading": h.heading_path,
                "score": h.score,
                "source": h.source,
            }
            for h in hits
        ]
        if as_json:
            typer.echo(json.dumps(out, ensure_ascii=False))
            return
        typer.echo(f"[{resolved}] {c.reason} / mode={mode} / agg={agg}")
        for i, h in enumerate(hits, start=1):
            typer.echo(
                f"{i:>2}. {h.doc_key}  §{h.heading_path or '-'}  "
                f"({h.source}, {h.score:.4f})"
            )
        return
    if resolved == "count":
        view = _guess_view(question)
        if view is None:
            typer.echo(
                f"どの集計か決められません。定義済み: {', '.join(sorted(VIEWS))}",
                err=True,
            )
            raise typer.Exit(code=2)
        rows = ask_view(view, resolve_dsn(dsn))
        out.update({"view": view, "rows": rows})
        if as_json:
            typer.echo(json.dumps(out, ensure_ascii=False, default=str))
            return
        typer.echo(f"[{resolved}] {c.reason} / 定義={view}")
        for r in rows:
            typer.echo("  " + "  ".join(f"{k2}={v}" for k2, v in r.items()))
        return
    if resolved == "asof":
        from dbr.features.asof import answer_asof

        try:
            # ① 探し物で文書を絞ってから時間で絞る。無ければ全文書 → 履歴で補う
            asof_ans = answer_asof(
                question,
                dsn=resolve_dsn(dsn),
                embedder=_embedder_or_exit(model),
                at=at_dt,
                k=k,
            )
        except LoopbackViolation as exc:
            raise _exit_on_loopback(exc) from None
        facts = asof_ans.hits
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
            for f in facts
        ]
        if as_json:
            typer.echo(json.dumps(out, ensure_ascii=False))
            return
        head = f"時点 {out['at']} の事実" if at_dt else "履歴（関連度順）"
        if asof_ans.fallback_to_history:
            head += "（その時点の記録なし → 関連する記録を履歴から・関連度順）"
        if asof_ans.scope == "chunks":
            scope = f"断片を絞った（質問に近い {len(asof_ans.chunks)} 断片）"
        elif asof_ans.scope == "docs":
            scope = f"文書を絞った: {', '.join(asof_ans.docs)}"
        else:
            scope = "全文書"
        typer.echo(f"[{resolved}] {c.reason} / {head} / {scope}")
        if not facts:
            typer.echo("  該当する記録なし")
        for f in facts:
            until = f" 〜 {f.valid_to.date().isoformat()}" if f.valid_to else ""
            flag = "（暫定）" if f.valid_source == "inferred" else ""
            typer.echo(
                f"  {f.valid_from.date().isoformat()}{until}{flag}  {f.doc_key}\n"
                f"      {f.value[:120]}"
            )
        return
    # overview
    from dbr.features.overview import answer as overview_answer
    from dbr.features.overview import narrate

    emb_ov = _embedder_or_exit(model)
    llm_obj = _llm_or_exit(llm) if llm != "none" else None
    try:
        ov = overview_answer(question, dsn=resolve_dsn(dsn), embedder=emb_ov)
    except LoopbackViolation as exc:
        raise _exit_on_loopback(exc) from None
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
    if as_json:
        typer.echo(json.dumps(out, ensure_ascii=False, default=str))
        return
    typer.echo(f"[{resolved}] {c.reason} / 対象 bundle: {', '.join(ov.bundles)}")
    for b in ov.bundle_summaries:
        typer.echo(f"\n■ {b['bundle']}（summary#{b['id']}）\n{b['text']}")
    if ov.doc_summaries:
        typer.echo("\n■ 質問に近い文書（上位）")
        for d in ov.doc_summaries:
            typer.echo(
                f"- [{d['doc']}]（summary#{d['id']}）\n  "
                + d["text"].replace("\n", "\n  ")
            )
    if nar is not None:
        typer.echo(f"\n■ LLM の回答（{nar.model}・{nar.seconds} 秒）\n{nar.text}")
        typer.echo("根拠外の言及: " + (", ".join(nar.unsupported) or "なし"))
    for w in ov.warnings:
        typer.echo(f"WARN: {w}", err=True)


def _guess_view(question: str) -> str | None:
    from dbr.features.count import guess_view

    return guess_view(question)


@app.command()
def bench(
    kind: Annotated[str, typer.Option("--kind")] = "find",
    modes: Annotated[str, typer.Option("--modes")] = (
        "fts,embed,embed_ctx,hybrid,hybrid_ctx,hybrid_ctx_rerank,embed_ctx_rerank"
    ),
    questions: Annotated[Path, typer.Option("--questions")] = REPO_ROOT
    / "docs"
    / "questions.md",
    out: Annotated[Path, typer.Option("--out")] = REPO_ROOT / "bench" / "results",
    ef_search: Annotated[int, typer.Option("--ef-search")] = 40,
    model: Annotated[str, typer.Option("--model")] = "intfloat/multilingual-e5-small",
    reranker: RerankerOpt = DEFAULT_RERANKER_NAME,
    label: Annotated[
        str | None,
        typer.Option("--label", help="ファイル名に付ける版ラベル [A-Za-z0-9_-]"),
    ] = None,
    answers: Annotated[
        Path,
        typer.Option("--answers", help="overview の回答を書く Markdown（K が採点）"),
    ] = REPO_ROOT / "docs" / "overview-answers.md",
    agg: Annotated[
        str,
        typer.Option("--agg", help="find の文書集約（既定 max＝v4〜v8 と比較可能）"),
    ] = "max",
    rerank_top: Annotated[
        int | None,
        typer.Option("--rerank-top", help="find: 並べ直す候補数（省略で既定）"),
    ] = None,
    llm: LlmOpt = "none",
    dsn: DsnOpt = None,
) -> None:
    """質問セットを流して指標を出す.

    --kind は find / sweep / hnsw / tune / count / asof / overview。
    """
    from dbr.features.bench import load_questions, run_find, save_json, to_markdown
    from dbr.features.bench.asof import asof_markdown, run_asof
    from dbr.features.bench.count import count_markdown, run_count
    from dbr.features.bench.hnsw import hnsw_markdown, run_hnsw
    from dbr.features.bench.overview import overview_markdown, run_overview
    from dbr.features.bench.report import LABEL_RE
    from dbr.features.bench.sweep import run_sweep, sweep_markdown
    from dbr.features.bench.tune import run_tune, tune_markdown
    from dbr.features.search import AGGS, MODES, NoEmbeddings

    if kind not in {"find", "sweep", "hnsw", "tune", "count", "asof", "overview"}:
        typer.echo(
            "--kind は find | sweep | hnsw | tune | count | asof | overview", err=True
        )
        raise typer.Exit(code=2)
    if label is not None and not LABEL_RE.fullmatch(label):
        typer.echo("--label は [A-Za-z0-9_-]{1,32}", err=True)
        raise typer.Exit(code=2)
    if agg not in AGGS:
        typer.echo(f"--agg は {AGGS} のいずれか", err=True)
        raise typer.Exit(code=2)
    qs = load_questions(questions)
    log = lambda m: typer.echo(m, err=True)  # noqa: E731 - 1行の配線
    try:
        if kind == "find":
            mode_list = [m.strip() for m in modes.split(",") if m.strip()]
            bad = [m for m in mode_list if m not in MODES]
            if bad:
                typer.echo(f"未知の mode: {bad}（{MODES}）", err=True)
                raise typer.Exit(code=2)
            emb = None if mode_list == ["fts"] else _embedder_or_exit(model)
            rr = (
                _reranker_or_exit(reranker)
                if any(m.endswith("_rerank") for m in mode_list)
                else None
            )
            result = run_find(
                qs,
                mode_list,  # type: ignore[arg-type]
                dsn=resolve_dsn(dsn),
                embedder=emb,
                ef_search=ef_search,
                repo=REPO_ROOT,
                log=log,
                reranker=rr,
                agg=agg,
                rerank_top=rerank_top,
            )
            text = to_markdown(result)
        elif kind == "count":
            result = run_count(qs, dsn=resolve_dsn(dsn), repo=REPO_ROOT)
            text = count_markdown(result)
        elif kind == "asof":
            result = run_asof(
                qs,
                dsn=resolve_dsn(dsn),
                embedder=_embedder_or_exit(model),
                repo=REPO_ROOT,
            )
            text = asof_markdown(result)
        elif kind == "overview":
            result = run_overview(
                qs,
                dsn=resolve_dsn(dsn),
                embedder=_embedder_or_exit(model),
                answers_path=answers,
                repo=REPO_ROOT,
                llm=_llm_or_exit(llm) if llm != "none" else None,
            )
            text = overview_markdown(result)
        elif kind == "sweep":
            result = run_sweep(
                qs,
                dsn=resolve_dsn(dsn),
                embedder=_embedder_or_exit(model),
                ef_search=ef_search,
                repo=REPO_ROOT,
            )
            text = sweep_markdown(result)
        elif kind == "tune":
            result = run_tune(
                qs,
                dsn=resolve_dsn(dsn),
                embedder=_embedder_or_exit(model),
                reranker=_reranker_or_exit(reranker),
                ef_search=ef_search,
                repo=REPO_ROOT,
            )
            text = tune_markdown(result)
        else:
            result = run_hnsw(
                qs,
                dsn=resolve_dsn(dsn),
                embedder=_embedder_or_exit(model),
                repo=REPO_ROOT,
            )
            text = hnsw_markdown(result)
    except NoEmbeddings as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=5) from None
    except LoopbackViolation as exc:
        raise _exit_on_loopback(exc) from None
    path = save_json(result, out, kind, label)
    typer.echo(text)
    typer.echo(f"\nJSON: {path}")


@app.command()
def reindex(
    bundle: Annotated[str, typer.Option("--bundle")],
    dsn: DsnOpt = None,
) -> None:
    """分かち書き規則を変えたあと、断片の lexemes を計算し直す（埋め込みは不変）."""
    from dbr.features.ingest import BUNDLES
    from dbr.features.ingest.reindex import run_reindex

    if bundle not in BUNDLES:
        typer.echo(f"--bundle は {sorted(BUNDLES)} のいずれか", err=True)
        raise typer.Exit(code=2)
    try:
        n = run_reindex(bundle, resolve_dsn(dsn))
    except LoopbackViolation as exc:
        raise _exit_on_loopback(exc) from None
    typer.echo(f"lexemes 更新 {n} 断片（{bundle}）")


@app.command()
def facts(
    bundle: Annotated[str, typer.Option("--bundle")],
    dsn: DsnOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """③ 時点: 取り込み済み断片から日付つきの事実を抽出して fact 表へ（冪等）."""
    from dbr.features.ingest import BUNDLES
    from dbr.features.ingest.facts import run_facts

    if bundle not in BUNDLES:
        typer.echo(f"--bundle は {sorted(BUNDLES)} のいずれか", err=True)
        raise typer.Exit(code=2)
    try:
        report = run_facts(bundle, resolve_dsn(dsn))
    except LoopbackViolation as exc:
        raise _exit_on_loopback(exc) from None
    if as_json:
        typer.echo(json.dumps(report.to_dict(), ensure_ascii=False))
    else:
        d = report.to_dict()
        typer.echo(
            f"explicit {d['explicit']} / dated_text {d['dated_text']} / "
            f"inferred {d['inferred']} / 日付なしで置けず {d['skipped_no_date']} / "
            f"recorded_at を valid_from で代用 {d['recorded_from_valid']}"
            f"（{bundle}）"
        )


@app.command()
def summarize(
    bundle: Annotated[str, typer.Option("--bundle")],
    check: Annotated[
        bool,
        typer.Option(
            "--check", help="書き換えず、陳腐化した要約を一覧（あれば exit 6）"
        ),
    ] = False,
    dsn: DsnOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """④ 全体: 抽出型の要約階層（bundle → document → section）を作り直す（冪等）."""
    from dataclasses import asdict

    from dbr.features.ingest import BUNDLES
    from dbr.features.ingest.summarize import run_summarize, stale_summaries

    if bundle not in BUNDLES:
        typer.echo(f"--bundle は {sorted(BUNDLES)} のいずれか", err=True)
        raise typer.Exit(code=2)
    if check:
        try:
            stale = stale_summaries(resolve_dsn(dsn), [bundle])
        except LoopbackViolation as exc:
            raise _exit_on_loopback(exc) from None
        if as_json:
            typer.echo(json.dumps([asdict(s) for s in stale], ensure_ascii=False))
        else:
            for s in stale:  # level と target_key だけ（本文は出さない）
                typer.echo(f"{s.level} {s.target_key} {s.reason}")
            typer.echo(f"陳腐化 {len(stale)} 件（{bundle}）")
        raise typer.Exit(code=6 if stale else 0)
    try:
        report = run_summarize(bundle, resolve_dsn(dsn))
    except LoopbackViolation as exc:
        raise _exit_on_loopback(exc) from None
    if as_json:
        typer.echo(json.dumps(report.to_dict(), ensure_ascii=False))
    else:
        typer.echo(
            f"section {report.sections} / document {report.documents} / "
            f"bundle {report.bundles}（{bundle}）"
        )


if __name__ == "__main__":
    app()
