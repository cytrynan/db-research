import pytest

from dbr.shared.rerank import get_reranker
from dbr.shared.rerank.fake import FakeReranker


def test_fake_is_deterministic_and_prefers_overlap() -> None:
    r = FakeReranker()
    a = r.score("メガネの度数", ["メガネの度数は右-3.0", "ネスプレッソのカプセル"])
    b = r.score("メガネの度数", ["メガネの度数は右-3.0", "ネスプレッソのカプセル"])
    assert a == b
    assert a[0] > a[1]
    assert r.score("x", []) == []


def test_get_reranker_fake() -> None:
    assert get_reranker("fake").name == "fake"


@pytest.mark.slow
def test_local_cross_encoder_ranks_relevant_passage_higher() -> None:
    r = get_reranker()
    s = r.score(
        "メガネの度数はどこに書いた？",
        ["視力とメガネの度数の記録", "ネスプレッソのカプセルの在庫"],
    )
    assert len(s) == 2 and s[0] > s[1]
