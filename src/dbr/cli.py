"""CLI `dbr`。配線だけを書き、ロジックはスライス側に置く.

exit code: 0 正常 / 1 その他 / 2 未定義の集計 / 3 ループバック違反 /
4 境界違反 (private.md 等)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from dbr.shared.db import LoopbackViolation, connect, resolve_dsn
from dbr.shared.db.migrate import migrate as run_migrations

app = typer.Typer(no_args_is_help=True, add_completion=False)

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


if __name__ == "__main__":
    app()
