"""ローカル LLM の入口。実装は transformers・CPU だけ。外部 API は無い.

D-13（ローカルモデルのみ）と同じ境界。

④ 全体の回答層で、要約階層から取った証拠だけを渡して短い日本語の回答を書かせる。
K の記録本文（chunk.body）は渡さない。
"""

from __future__ import annotations

from typing import Protocol

DEFAULT_LLM = "Qwen/Qwen2.5-1.5B-Instruct"
FAKE_LLM = "fake"
NO_LLM = "none"


class LLMUnavailable(Exception):
    """モデルが読み込めない（未取得・依存不足）."""


class LLM(Protocol):
    name: str

    def generate(self, system: str, user: str, *, max_new_tokens: int = 400) -> str: ...


def get_llm(name: str = DEFAULT_LLM) -> LLM:
    """名前から実装を返す。`fake` は決定的ダミー（配線のテスト用）."""
    if name == FAKE_LLM:
        from dbr.shared.llm.fake import FakeLLM

        return FakeLLM()
    from dbr.shared.llm.local import LocalCausalLM

    return LocalCausalLM(name)


__all__ = [
    "DEFAULT_LLM",
    "FAKE_LLM",
    "LLM",
    "NO_LLM",
    "LLMUnavailable",
    "get_llm",
]
