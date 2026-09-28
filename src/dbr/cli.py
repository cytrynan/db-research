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


@app.command()
def ask(
    question: Annotated[str, typer.Argument()],
    mode: Annotated[str, typer.Option("--mode")] = "hybrid_ctx",
    kind: Annotated[str, typer.Option("--kind", help="auto | find | count")] = "auto",
    k: Annotated[int, typer.Option("--k")] = 5,
    model: Annotated[str, typer.Option("--model")] = "intfloat/multilingual-e5-small",
    dsn: DsnOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """型判定 → 該当する道具で答える（find=検索 / count=ビュー / 他=未実装）."""
    from dbr.features.classify import RuleClassifier
    from dbr.features.count import VIEWS, ask_view
    from dbr.features.search import MODES, NoEmbeddings, dedupe_by_document, search

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
        emb = None if mode == "fts" else _embedder_or_exit(model)
        try:
            hits = dedupe_by_document(
                search(question, mode=mode, dsn=resolve_dsn(dsn), k=k * 5, embedder=emb)  # type: ignore[arg-type]
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
        typer.echo(f"[{resolved}] {c.reason} / mode={mode}")
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
    typer.echo(
        f"[{resolved}] {c.reason} / この型はまだ実装していません（次の作業単位）"
    )


def _guess_view(question: str) -> str | None:
    """② の質問 → ビュー名。語彙の固定対応だけ（LLM に SQL を書かせない）."""
    q = question.lower()
    if "verified" in q or "確認済" in q or "未確認" in q:
        return "v_unverified"
    if "stale" in q or "期限" in q:
        return "v_stale"
    if "type" in q or "種別" in q:
        return "v_by_type"
    if "ファイル" in q or "記録" in q or "件" in q:
        return "v_by_bundle"
    return None


@app.command()
def bench(
    kind: Annotated[str, typer.Option("--kind")] = "find",
    modes: Annotated[str, typer.Option("--modes")] = "fts,embed,hybrid,hybrid_ctx",
    questions: Annotated[Path, typer.Option("--questions")] = REPO_ROOT
    / "docs"
    / "questions.md",
    out: Annotated[Path, typer.Option("--out")] = REPO_ROOT / "bench" / "results",
    ef_search: Annotated[int, typer.Option("--ef-search")] = 40,
    model: Annotated[str, typer.Option("--model")] = "intfloat/multilingual-e5-small",
    dsn: DsnOpt = None,
) -> None:
    """質問セットを方式ごとに流し、recall@5 / recall@20 / MRR を JSON と表で出す."""
    from dbr.features.bench import load_questions, run_find, save_json, to_markdown
    from dbr.features.search import MODES, NoEmbeddings

    if kind != "find":
        typer.echo("この単位で測れるのは --kind find だけです", err=True)
        raise typer.Exit(code=2)
    mode_list = [m.strip() for m in modes.split(",") if m.strip()]
    bad = [m for m in mode_list if m not in MODES]
    if bad:
        typer.echo(f"未知の mode: {bad}（{MODES}）", err=True)
        raise typer.Exit(code=2)
    emb = None if mode_list == ["fts"] else _embedder_or_exit(model)
    try:
        result = run_find(
            load_questions(questions),
            mode_list,  # type: ignore[arg-type]
            dsn=resolve_dsn(dsn),
            embedder=emb,
            ef_search=ef_search,
            repo=REPO_ROOT,
        )
    except NoEmbeddings as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=5) from None
    except LoopbackViolation as exc:
        raise _exit_on_loopback(exc) from None
    path = save_json(result, out, kind)
    typer.echo(to_markdown(result))
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


if __name__ == "__main__":
    app()
