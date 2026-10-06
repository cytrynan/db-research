"""scope の既定値だけを置く軽いモジュール（CLI の起動時に search/psycopg を引き込まないため）.

`features/scope/__init__.py` が `search.Hit` を import するので、既定値をそこから取ると
`dbr ask`（常駐経由）でも psycopg と検索モジュールが読み込まれていた（2026-10-06 実測:
import 時間の約 0.35 秒）。CLI と ask 層はここから取る。値の意味は `__init__.py` の D-16 注記。
"""

from __future__ import annotations

# D-16（2026-09-30・v10）: none 0.90/0.861 → filter・boost(0.5〜2.0) はすべて 1.00/0.883。
# 同点なので柔らかい boost を既定にし、w は Q19 の上位 5 が全部 references になる最小の 1.0
DEFAULT_SCOPE: str = "boost"
DEFAULT_BOOST: float = 1.0

__all__ = ["DEFAULT_BOOST", "DEFAULT_SCOPE"]
