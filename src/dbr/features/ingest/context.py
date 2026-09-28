"""断片の頭に付ける文脈文（Contextual Retrieval のテンプレ版）.

LLM 生成版は次の作業単位で差し替える。関数1つに閉じておく。
"""

from __future__ import annotations


def context_for(
    bundle: str, rel_path: str, heading_path: str, description: str | None
) -> str:
    where = f"{bundle}/{rel_path}"
    if heading_path:
        where += f" — {heading_path}"
    if description:
        return f"{where}（{description}）"
    return where
