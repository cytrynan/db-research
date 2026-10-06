"""Hugging Face Hub への問い合わせを既定で切る（D-13 の「ローカルのみ」を通信面でも守る）.

huggingface_hub は import 時に環境変数を読むので、torch / sentence_transformers /
transformers を import する**前**に呼ぶ（ローカルモデルを読む 3 か所の直前で呼んでいる）。
モデルが未取得のときだけ `DBR_HF_ONLINE=1` を付けて 1 回取得する。

実測（2026-10-05）: オンライン既定だと `dbr ask` 1 回ごとに Hub への確認が走り、
約 7 秒と「unauthenticated requests to the HF Hub」の警告が出ていた。
"""

from __future__ import annotations

import os

ENV_ONLINE = "DBR_HF_ONLINE"
OFFLINE_VARS: tuple[str, ...] = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
ONLINE_HINT = (
    f"モデルが未取得なら環境変数 {ENV_ONLINE}=1 を付けて 1 回だけ取得してください"
    "（既定はオフライン）"
)


def apply_offline_default() -> bool:
    """`DBR_HF_ONLINE=1` でなければオフライン系の環境変数を setdefault する.

    戻り値はオフラインにしたか（既に利用者が明示した値は上書きしない）。
    """
    if os.environ.get(ENV_ONLINE, "") == "1":
        return False
    for var in OFFLINE_VARS:
        os.environ.setdefault(var, "1")
    return True


__all__ = ["ENV_ONLINE", "OFFLINE_VARS", "ONLINE_HINT", "apply_offline_default"]
