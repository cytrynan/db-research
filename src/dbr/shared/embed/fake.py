"""決定的なダミー埋め込み。DB 側（冪等・検索の配線）をモデル無しで検証するため.

同じ文には同じベクトル、違う文には（ほぼ）直交するベクトルを返す。
意味の近さは表現しない＝品質の測定には使わない。
"""

from __future__ import annotations

import hashlib

import numpy as np

from dbr.shared.embed import DIMS, FAKE_MODEL


class FakeEmbedder:
    name = FAKE_MODEL
    dims = DIMS

    @staticmethod
    def _vec(text: str) -> list[float]:
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(DIMS)
        v /= np.linalg.norm(v)
        return [float(x) for x in v]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)
