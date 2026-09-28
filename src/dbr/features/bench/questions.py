"""docs/questions.md の表を読む。正解はバッククォート内の bundle/rel_path.md だけ."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

BUNDLE_PREFIX = r"(?:references|dev|stock|tax|scout|memory|experiments)"
PATH_RE = re.compile(rf"`({BUNDLE_PREFIX}/[^`]+?\.md)`")
ROW_RE = re.compile(r"^\|\s*(Q\d+)\s*\|")


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    kind: str
    expected: tuple[str, ...]  # 'references/health.md' 形式（bundle/rel_path）


def parse_row(line: str) -> Question | None:
    if not ROW_RE.match(line):
        return None
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) < 4:
        return None
    qid, text, kind, expected = cells[0], cells[1], cells[2], cells[3]
    return Question(qid, text, kind, tuple(PATH_RE.findall(expected)))


def load_questions(path: Path) -> list[Question]:
    out: list[Question] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        q = parse_row(line)
        if q is not None:
            out.append(q)
    return out
