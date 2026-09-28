"""Markdown を見出し単位の断片に分ける.

- 見出しは `#`〜`###`。コードフェンス内の `#` は見出し扱いしない
- 1断片が max_tokens を超えたら段落（空行）境界で分割する
- トークン数は近似（文字数/2）。埋め込みモデルの tokenizer は次の作業単位で差し替える
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HEADING = re.compile(r"^(#{1,3})\s+(.*\S)\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class RawChunk:
    ordinal: int
    heading_path: str
    body: str
    tokens: int


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 2)


def _sections(markdown: str) -> list[tuple[str, list[str]]]:
    """(heading_path, lines) の列。先頭の見出し前は heading_path ''."""
    stack: list[str] = []
    sections: list[tuple[str, list[str]]] = [("", [])]
    in_fence = False
    for line in markdown.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            sections[-1][1].append(line)
            continue
        m = None if in_fence else HEADING.match(line)
        if m:
            level = len(m.group(1))
            stack = [*stack[: level - 1], m.group(2)]
            sections.append((" > ".join(stack), []))
        else:
            sections[-1][1].append(line)
    return sections


def _split_paragraphs(text: str, max_tokens: int) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        candidate = "\n\n".join([*current, para])
        if current and estimate_tokens(candidate) > max_tokens:
            parts.append("\n\n".join(current))
            current = [para]
        else:
            current.append(para)
    if current:
        parts.append("\n\n".join(current))
    return parts


def split(markdown: str, *, max_tokens: int = 800) -> list[RawChunk]:
    chunks: list[RawChunk] = []
    for heading_path, lines in _sections(markdown):
        body = "\n".join(lines).strip()
        if not body:
            continue
        pieces = (
            [body]
            if estimate_tokens(body) <= max_tokens
            else _split_paragraphs(body, max_tokens)
        )
        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue
            chunks.append(
                RawChunk(
                    ordinal=len(chunks),
                    heading_path=heading_path,
                    body=piece,
                    tokens=estimate_tokens(piece),
                )
            )
    return chunks
