"""日本語の分かち書き（SudachiPy）。取り込みと検索が**同じ関数**を使う.

- NFKC 正規化 → Sudachi split mode C → normalized_form を小文字化
  （normalized_form は「メガネ」→「眼鏡」のように表記ゆれを寄せる。実測 2026-09-29）
- 記号・空白だけのトークンは落とす
- 辞書の読み込みは重いので tokenizer はプロセスで 1 回だけ作る
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache
from typing import Any

SUDACHI_DICT = "sudachidict_core"
# 索引・検索語から落とす品詞（Sudachi の品詞大分類）
FUNCTION_POS = frozenset({"助詞", "助動詞", "補助記号", "記号", "空白"})


class TokenizerUnavailable(Exception):
    """Sudachi 辞書が使えない（uv sync 未実行など）."""


@lru_cache(maxsize=1)
def _tokenizer() -> tuple[Any, Any]:
    try:
        from sudachipy import dictionary, tokenizer
    except ImportError as exc:  # pragma: no cover - 環境依存
        raise TokenizerUnavailable(str(exc)) from exc
    try:
        # `.create()` は DeprecationWarning（→ `.tokenizer()`。sudachipy 0.6 系）
        tok = dictionary.Dictionary(
            dict=SUDACHI_DICT.removeprefix("sudachidict_")
        ).tokenizer()
    except Exception as exc:  # pragma: no cover - 環境依存
        raise TokenizerUnavailable(f"{SUDACHI_DICT}: {exc}") from exc
    return tok, tokenizer.Tokenizer.SplitMode.C


def dict_version() -> str:
    """測定結果 JSON に記録する辞書名（再現性のため）."""
    try:
        from importlib.metadata import version

        return f"{SUDACHI_DICT}=={version(SUDACHI_DICT.replace('_', '-'))}"
    except Exception:  # pragma: no cover
        return SUDACHI_DICT


def tokenize(text: str) -> list[str]:
    tok, mode = _tokenizer()
    # NFKC: 全角英数・半角カナを畳む（検索語と索引で同じ関数を使うので片側だけ違わない）
    normalized = unicodedata.normalize("NFKC", text)
    out: list[str] = []
    for m in tok.tokenize(normalized, mode):
        surface = m.normalized_form().lower().strip()
        if not surface:
            continue
        # 機能語（助詞・助動詞・記号）は索引しない。AND 検索だと「の」「に」「た」が
        # 入るだけで該当断片がほぼ無くなる（2026-09-29 初回 bench: fts recall@5=0.20）
        if m.part_of_speech()[0] in FUNCTION_POS:
            continue
        # 記号・空白だけのトークンは索引しない
        if all(unicodedata.category(ch)[0] in {"P", "Z", "C", "S"} for ch in surface):
            continue
        out.append(surface)
    return out


def lexemes(text: str) -> str:
    """tsvector に渡す空白区切りの語列."""
    return " ".join(tokenize(text))
