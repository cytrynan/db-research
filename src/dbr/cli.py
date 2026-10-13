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

# 起動時に psycopg / 検索モジュールを読まない（常駐経由の ask は urllib だけで済む。
# 2026-10-06 実測: この 2 行で import 時間 約 0.35 秒）。DB を触るコマンドは中で import する
from dbr.features.scope.defaults import DEFAULT_BOOST, DEFAULT_SCOPE
from dbr.shared.db.dsn import LoopbackViolation, resolve_dsn

app = typer.Typer(no_args_is_help=True, add_completion=False)

# Windows の既定コンソール（cp932）は「—」等で UnicodeEncodeError になり
# JSON 出力が落ちる（2026-09-29 実測）。標準出力・エラーを UTF-8 に固定する
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

DsnOpt = Annotated[
    str | None,
    typer.Option(
        "--dsn", help="接続文字列。省略時は環境変数 DBR_DSN → リポ直下 .env の DBR_DSN"
    ),
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
    from dbr.shared.db import connect
    from dbr.shared.db.migrate import migrate as run_migrations

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
ScopeOpt = Annotated[
    str,
    typer.Option(
        "--scope", help="bundle の絞り込み none | filter | boost（質問の語で推定）"
    ),
]
BoostOpt = Annotated[
    float, typer.Option("--boost-w", help="scope=boost の重み（(1+w) 倍）")
]


def _llm_or_exit(name: str) -> Any:
    from dbr.shared.llm import LLMUnavailable, get_llm

    try:
        return get_llm(name)
    except LLMUnavailable as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=5) from None


NoDaemonOpt = Annotated[
    bool,
    typer.Option(
        "--no-daemon",
        help="常駐（dbr serve）を使わず単発で計算する（環境変数 DBR_NO_DAEMON=1 と同じ）",
    ),
]
PortOpt = Annotated[
    int | None,
    typer.Option("--port", help="常駐のポート。省略時は環境変数 DBR_PORT か 47821"),
]


def _port_or_exit(port: int | None) -> int:
    from dbr.features.serve import port_from_env

    try:
        return port if port is not None else port_from_env()
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from None


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
    scope: ScopeOpt = DEFAULT_SCOPE,  # D-16（v10）
    boost_w: BoostOpt = DEFAULT_BOOST,
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
    no_daemon: NoDaemonOpt = False,
    port: PortOpt = None,
    dsn: DsnOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """型判定 → 該当する道具で答える（find / count / asof / overview）.

    語彙に当たらない質問は ① 探し物として検索し、推定であることを明示する（D-17）。
    計算本体は features/ask。既定では常駐（dbr serve）に投げ、居なければ起こす（D-18）。
    --dsn を明示したときは常駐を使わない（常駐は自分の DSN で動いているため）。
    """
    from dbr.features.ask import AskError, AskOptions, format_text, stderr_notes
    from dbr.features.serve.client import ask_remote, daemon_disabled, ensure_daemon

    opts = AskOptions(
        kind=kind,
        mode=mode,
        agg=agg,
        rerank_top=rerank_top,
        scope=scope,
        boost_w=boost_w,
        k=k,
        model=model,
        reranker=reranker,
        at=at,
        llm=llm,
    )
    use_daemon = not (no_daemon or daemon_disabled() or dsn is not None)
    out: dict[str, Any] | None = None
    try:
        if use_daemon:
            p = _port_or_exit(port)
            if ensure_daemon(p):
                out = ask_remote(question, opts, port=p, client="cli")
            else:
                typer.echo(
                    f"WARN: 常駐を {p} 番で起こせなかったので単発で計算します"
                    "（~/.dbr/serve.log を確認）",
                    err=True,
                )
        if out is None:
            out = _ask_local(question, opts, dsn)
    except AskError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=exc.code) from None
    for note in stderr_notes(out):
        typer.echo(note, err=True)
    if as_json:
        typer.echo(json.dumps(out, ensure_ascii=False, default=str))
        return
    typer.echo(format_text(out))


def _ask_local(question: str, opts: Any, dsn: str | None) -> dict[str, Any]:
    """単発経路（常駐を通らない）。常駐側のログに乗らないので、ここで利用ログを 1 行残す（client=cli-local）."""
    import time

    from dbr.features.ask import AskError, answer
    from dbr.features.serve.usage import log_request
    from dbr.shared.embed import get_embedder
    from dbr.shared.llm import get_llm
    from dbr.shared.rerank import get_reranker

    t0 = time.monotonic()
    try:
        out = answer(
            question,
            opts,
            dsn=resolve_dsn(dsn),
            embedder_for=get_embedder,
            reranker_for=get_reranker,
            llm_for=get_llm,
        )
    except AskError as exc:
        log_request(
            client="cli-local",
            question=question,
            opts=opts.to_dict(),
            status="error",
            ms=(time.monotonic() - t0) * 1000.0,
            code=exc.code,
            error=str(exc),
        )
        raise
    except Exception as exc:  # DB 接続失敗・ループバック違反等も 1 行残す（受入検証 2026-10-13 必須 1）
        log_request(
            client="cli-local",
            question=question,
            opts=opts.to_dict(),
            status="error",
            ms=(time.monotonic() - t0) * 1000.0,
            code=1,
            error=f"{type(exc).__name__}: {exc}",
        )
        raise
    log_request(
        client="cli-local",
        question=question,
        opts=opts.to_dict(),
        status="ok",
        ms=(time.monotonic() - t0) * 1000.0,
        out=out,
    )
    return out


@app.command()
def serve(
    port: PortOpt = None,
    sync_interval: Annotated[
        int,
        typer.Option(
            "--sync-interval", help="同期の間隔（分）。起動直後に 1 回、0 で無効"
        ),
    ] = 30,
    stop: Annotated[
        bool, typer.Option("--stop", help="動いている常駐を止める")
    ] = False,
    no_auto_recover: Annotated[
        bool,
        typer.Option(
            "--no-auto-recover",
            help="DB に届かない時の自動復旧（docker restart/start）をしない（DBR_NO_AUTO_RECOVER=1 と同じ・D-21）",
        ),
    ] = False,
    dsn: DsnOpt = None,
) -> None:
    """常駐サーバー（127.0.0.1 のみ）。埋め込みモデルを 1 回読み、ask / sync に答える（D-18）."""
    from dbr.features.serve import DEFAULT_SYNC_INTERVAL_MIN
    from dbr.features.serve import serve as run_serve
    from dbr.features.serve.client import health, stop_daemon

    p = _port_or_exit(port)
    if stop:
        typer.echo("停止しました" if stop_daemon(p) else f"{p} 番に常駐はいません")
        return
    if health(p) is not None:
        typer.echo(f"{p} 番で既に動いています", err=True)
        raise typer.Exit(code=1)
    if sync_interval < 0:
        typer.echo("--sync-interval は 0 以上", err=True)
        raise typer.Exit(code=2)
    try:
        resolved = resolve_dsn(dsn)
        from dbr.shared.db import assert_loopback

        assert_loopback(resolved)  # 起動時に検査（接続は最初の質問で）
    except LoopbackViolation as exc:
        raise _exit_on_loopback(exc) from None
    _ = DEFAULT_SYNC_INTERVAL_MIN
    from dbr.shared.embed import EmbedderUnavailable

    try:
        run_serve(
            p,
            resolved,
            sync_interval_min=sync_interval,
            auto_recover=not no_auto_recover,
        )
    except (
        EmbedderUnavailable
    ) as exc:  # 起動時のモデル読み込み失敗も単発 ask と同じ exit 5
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=5) from None
    except OSError as exc:
        # bind 失敗（別の常駐が先に取った）は exit 6。client.ensure_daemon はこの番号だけ待ち続ける
        import errno

        if exc.errno == errno.EADDRINUSE or getattr(exc, "winerror", None) == 10048:
            typer.echo(
                f"{p} 番は使用中です（別の常駐が起動中か動いています）", err=True
            )
            raise typer.Exit(code=6) from None
        raise


@app.command()
def sync(
    bundle: Annotated[
        list[str] | None,
        typer.Option("--bundle", help="対象 bundle（複数可）。省略で全 7 bundle"),
    ] = None,
    model: Annotated[str, typer.Option("--model")] = "intfloat/multilingual-e5-small",
    no_daemon: NoDaemonOpt = False,
    port: PortOpt = None,
    dsn: DsnOpt = None,
    as_json: JsonOpt = False,
) -> None:
    """正本フォルダの変更・新規・削除を DB に反映（取り込み → 埋め込み → fact → summary・冪等・D-19）.

    常駐が動いていて --bundle 指定が無ければ常駐に任せる（同時実行を避ける）。
    """
    from dbr.features.ingest import BUNDLES, PersonalDataRejected
    from dbr.features.serve.client import daemon_disabled, health, sync_remote
    from dbr.features.sync import run_sync

    if bundle:
        bad = [b for b in bundle if b not in BUNDLES]
        if bad:
            typer.echo(f"--bundle は {sorted(BUNDLES)} のいずれか: {bad}", err=True)
            raise typer.Exit(code=2)
    use_daemon = not (no_daemon or daemon_disabled() or dsn is not None or bundle)
    if use_daemon:
        p = _port_or_exit(port)
        if health(p) is not None:
            report = sync_remote(p)
            _print_sync(report, as_json)
            return
    try:
        rep = run_sync(
            resolve_dsn(dsn),
            _embedder_or_exit(model),
            bundles=bundle or None,
            log=lambda m: typer.echo(m, err=True),
        )
    except LoopbackViolation as exc:
        raise _exit_on_loopback(exc) from None
    except PersonalDataRejected as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=4) from None
    _print_sync(rep.to_dict(), as_json)


def _print_sync(report: dict[str, Any], as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(report, ensure_ascii=False, default=str))
        return
    for b in report.get("bundles", []):
        if b.get("skipped_missing_root"):
            typer.echo(f"{b['bundle']}: skip（正本フォルダなし {b['root']}）")
            continue
        typer.echo(
            f"{b['bundle']}: 新規 {b['inserted']} / 更新 {b['updated']} / "
            f"削除 {b['pruned']} / 不変 {b['unchanged']} / 埋め込み "
            f"{b['embedded_plain']}+{b['embedded_ctx']}"
            + (f" / 再構築 {b['rebuilt_reason']}" if b.get("rebuilt_reason") else "")
        )
    typer.echo(
        f"変更 {'あり' if report.get('changed') else 'なし'}（{report.get('seconds')} 秒）"
    )


@app.command()
def mcp() -> None:
    """エージェントの入口: stdio の MCP サーバー（ask / count / sync / health。常駐へ中継）."""
    from dbr.features.mcp_server import run_stdio

    run_stdio()


@app.command()
def usage(
    days: Annotated[int, typer.Option("--days", help="直近 N 日（既定 7）")] = 7,
    path: Annotated[
        Path | None,
        typer.Option("--path", help="usage.jsonl の場所（既定 ~/.dbr/usage.jsonl）"),
    ] = None,
    as_json: JsonOpt = False,
) -> None:
    """利用ログを集計する: 呼び出し元×結果・フォールバック率・応答時間 p50/p90・0 件だった質問・エラー（D-20）."""
    from dbr.features.serve.usage import format_summary, iter_records, summarize

    try:
        summary = summarize(iter_records(path), days=days)
    except (ValueError, OverflowError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from None
    if as_json:
        typer.echo(json.dumps(summary, ensure_ascii=False, default=str))
        return
    typer.echo(format_summary(summary))


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
    scope: ScopeOpt = "none",  # 既定 none＝v4〜v8 と比較できるベースライン
    boost_w: BoostOpt = DEFAULT_BOOST,  # ask と同じ定数（受入検証 R3）
    dsn: DsnOpt = None,
) -> None:
    """質問セットを流して指標を出す.

    --kind は find / sweep / hnsw / tune / scope / count / asof / overview。
    """
    from dbr.features.bench import load_questions, run_find, save_json, to_markdown
    from dbr.features.bench.asof import asof_markdown, run_asof
    from dbr.features.bench.count import count_markdown, run_count
    from dbr.features.bench.hnsw import hnsw_markdown, run_hnsw
    from dbr.features.bench.overview import overview_markdown, run_overview
    from dbr.features.bench.report import LABEL_RE
    from dbr.features.bench.scope import run_scope, scope_markdown
    from dbr.features.bench.sweep import run_sweep, sweep_markdown
    from dbr.features.bench.tune import run_tune, tune_markdown
    from dbr.features.scope import SCOPES
    from dbr.features.search import AGGS, MODES, NoEmbeddings

    if kind not in {
        "find",
        "sweep",
        "hnsw",
        "tune",
        "scope",
        "count",
        "asof",
        "overview",
    }:
        typer.echo(
            "--kind は find | sweep | hnsw | tune | scope | count | asof | overview",
            err=True,
        )
        raise typer.Exit(code=2)
    if scope not in SCOPES:
        typer.echo(f"--scope は {SCOPES} のいずれか", err=True)
        raise typer.Exit(code=2)
    if label is not None and not LABEL_RE.fullmatch(label):
        typer.echo("--label は [A-Za-z0-9_-]{1,32}", err=True)
        raise typer.Exit(code=2)
    if agg not in AGGS:
        typer.echo(f"--agg は {AGGS} のいずれか", err=True)
        raise typer.Exit(code=2)
    if llm != "none" and kind != "overview":
        typer.echo(
            f"WARN: --llm は --kind overview だけで使う（{kind} では無視）", err=True
        )
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
                scope=scope,
                boost_w=boost_w,
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
        elif kind == "scope":
            result = run_scope(
                qs,
                dsn=resolve_dsn(dsn),
                embedder=_embedder_or_exit(model),
                repo=REPO_ROOT,
            )
            text = scope_markdown(result)
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
