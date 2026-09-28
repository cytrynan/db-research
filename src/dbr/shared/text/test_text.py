"""分かち書きのユニット。辞書は uv sync で入るので通常テスト."""

from dbr.shared.text import lexemes, tokenize


def test_tokenize_japanese_splits_into_words() -> None:
    toks = tokenize("メガネの度数をどこに書いた？")
    assert tokenize("メガネ")[0] in toks  # 正規形（実測では「眼鏡」）で入る
    assert "度数" in toks
    # 機能語（助詞・助動詞）は落とす。残るのは内容語だけ
    assert (
        "の" not in toks and "を" not in toks and "に" not in toks and "た" not in toks
    )
    assert "？" not in toks  # 記号は落とす


def test_tokenize_normalizes_width_and_case() -> None:
    assert tokenize("ＰＤＦのＯＣＲ") == tokenize("PDFのOCR")
    assert "pdf" in tokenize("PDF")


def test_orthographic_variants_are_merged_by_normalized_form() -> None:
    # Sudachi の normalized_form は表記ゆれを寄せる（眼鏡＝メガネ）。
    # 当初「別語のまま」と想定したが実測で逆だったので事実として固定する
    assert tokenize("メガネ") == tokenize("眼鏡")


def test_lexemes_is_space_joined() -> None:
    lx = lexemes("花粉症の薬")
    assert " " in lx
    assert lx.split() == tokenize("花粉症の薬")


def test_empty_and_symbol_only() -> None:
    assert tokenize("") == []
    assert tokenize("！！！  …") == []
