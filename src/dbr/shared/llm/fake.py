"""決定的なダミー LLM。配線のテスト用（意味は見ない）.

証拠（user の「- 」で始まる行）の先頭 3 件を切り貼りして返す。証拠に無い語は作らない。
"""

from __future__ import annotations

from dbr.shared.llm import FAKE_LLM


class FakeLLM:
    name = FAKE_LLM

    def generate(self, system: str, user: str, *, max_new_tokens: int = 400) -> str:
        lines = [ln[2:].strip() for ln in user.splitlines() if ln.startswith("- ")][:3]
        if not lines:
            return "一覧には見当たらない。"
        return "一覧から: " + " / ".join(ln[:60] for ln in lines)
