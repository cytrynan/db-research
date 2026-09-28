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


if __name__ == "__main__":
    app()
