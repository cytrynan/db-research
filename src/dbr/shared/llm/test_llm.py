from dbr.shared.llm import FAKE_LLM, get_llm


def test_fake_llm_is_deterministic_and_copies_only_evidence_lines() -> None:
    llm = get_llm(FAKE_LLM)
    user = "質問: x\n\n一覧:\n【dev】dev: 文書 53\n- a.md: 手順\n- b.md: メモ\n\n回答:"
    a = llm.generate("sys", user)
    assert a == llm.generate("sys", user) == "一覧から: a.md: 手順 / b.md: メモ"
    assert get_llm(FAKE_LLM).generate("sys", "一覧なし") == "一覧には見当たらない。"
