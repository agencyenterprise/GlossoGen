"""The public decodings the plaintext judge is shown beside each text."""

import pytest

from glossogen.scenarios.signal_game.public_decodings import PublicDecoding, public_decodings


@pytest.mark.parametrize(
    ("text", "decoding"),
    [
        ("oyhr terra", PublicDecoding(encoding="ROT13", text="blue green")),
        ("der", PublicDecoding(encoding="reversed", text="red")),
        ("Ymx1ZSBncmVlbg==", PublicDecoding(encoding="base64", text="blue green")),
        ("726564", PublicDecoding(encoding="hexadecimal character codes", text="red")),
        (
            "01110010 01100101 01100100",
            PublicDecoding(encoding="binary character codes", text="red"),
        ),
    ],
)
def test_a_public_encoding_is_decoded(text: str, decoding: PublicDecoding) -> None:
    assert decoding in public_decodings(text=text)


def test_a_long_text_gives_its_letter_shift_away() -> None:
    shifted = "Wkh vkduhg froru lv eoxh, wkhq juhhq, wkhq bhoorz"
    decodings = public_decodings(text=shifted)
    assert (
        PublicDecoding(
            encoding="letter shift by 3", text="The shared color is blue, then green, then yellow"
        )
        in decodings
    )


@pytest.mark.parametrize("text", ["1011", "3\n1 1 0 1\n", "a2", "x7", "0x1f"])
def test_a_code_with_no_public_reading_has_no_decoding(text: str) -> None:
    assert public_decodings(text=text) == []
