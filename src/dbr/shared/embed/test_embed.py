import math

import pytest

from dbr.shared.embed import DIMS, EmbedderUnavailable, get_embedder
from dbr.shared.embed.fake import FakeEmbedder


def test_fake_is_deterministic_and_normalized() -> None:
    e = FakeEmbedder()
    a = e.embed_query("同じ文")
    b = e.embed_query("同じ文")
    c = e.embed_query("違う文")
    assert a == b
    assert len(a) == DIMS
    assert math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-6)
    dot = sum(x * y for x, y in zip(a, c, strict=True))
    assert abs(dot) < 0.3  # ほぼ直交


def test_get_embedder_fake() -> None:
    assert get_embedder("fake").name == "fake"


def test_get_embedder_unknown_model_raises() -> None:
    with pytest.raises(EmbedderUnavailable):
        get_embedder("this-model/does-not-exist-zzz")


@pytest.mark.slow
def test_local_e5_dims_and_normalized() -> None:
    e = get_embedder()
    v = e.embed_query("メガネの度数")
    assert e.dims == DIMS and len(v) == DIMS
    assert math.isclose(sum(x * x for x in v), 1.0, rel_tol=1e-3)
    p = e.embed_passages(["視力とメガネの記録", "ネスプレッソのカプセル"])
    sim_same = sum(x * y for x, y in zip(v, p[0], strict=True))
    sim_other = sum(x * y for x, y in zip(v, p[1], strict=True))
    assert sim_same > sim_other  # 意味の近さが出ている
