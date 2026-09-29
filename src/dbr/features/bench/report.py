"""測定結果の JSON（一次記録）と Markdown 表（転記用）."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def git_sha(repo: Path) -> str:
    """HEAD の短い SHA。未コミットの変更があれば `-dirty` を付ける（生成元の特定用）."""
    try:
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return f"{head}-dirty" if status else head
    except Exception:  # pragma: no cover - git 無し
        return "unknown"


LABEL_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def result_path(out_dir: Path, kind: str, label: str | None = None) -> Path:
    """`YYYYMMDD-<kind>[-<label>].json`。label はファイル名に入るので語彙を限定する."""
    if label is not None and not LABEL_RE.match(label):
        raise ValueError("label は [A-Za-z0-9_-]{1,32}")
    day = datetime.now().strftime("%Y%m%d")
    suffix = f"-{label}" if label else ""
    return out_dir / f"{day}-{kind}{suffix}.json"


def save_json(
    result: dict[str, Any], out_dir: Path, kind: str, label: str | None = None
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = result_path(out_dir, kind, label)
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def to_markdown(result: dict[str, Any]) -> str:
    modes: dict[str, Any] = result["modes"]
    lines = [
        f"測定: {result['date']} / git {result['git_sha']} / model {result['model']} / "
        f"{result['sudachi_dict']} / ef_search={result['ef_search']} / "
        f"N={result['question_count']}",
        "",
        "| 方式 | recall@5 | recall@20 | MRR | 未ヒット |",
        "|---|---|---|---|---|",
    ]
    for mode, m in modes.items():
        miss = sum(1 for p in m["per_question"] if p["rank"] is None)
        lines.append(
            f"| {mode} | {m['recall@5']:.2f} | {m['recall@20']:.2f} | "
            f"{m['mrr']:.3f} | {miss} |"
        )
    lines += ["", "| # | " + " | ".join(modes) + " |", "|---|" + "---|" * len(modes)]
    ids = [p["id"] for p in next(iter(modes.values()))["per_question"]]
    for i, qid in enumerate(ids):
        cells = [str(m["per_question"][i]["rank"] or "-") for m in modes.values()]
        lines.append(f"| {qid} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
