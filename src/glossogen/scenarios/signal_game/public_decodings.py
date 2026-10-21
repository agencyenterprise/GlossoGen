"""Public decodings of a text: what it reads as under encodings that need no agreed key.

A player can hide a message from a reader who does not try to decode it, in ROT13,
reversed, or as base64, hexadecimal or binary character codes. None of these needs a
key the two players agreed, so the plaintext judge is shown what each turns the text
into, and judges the text plaintext when a decoding is. Another letter shift needs
its shift agreed, but a long enough text gives it away to letter frequencies, so the
likeliest shift is shown for texts of ``MIN_SHIFT_LETTERS`` letters or more. Only
decodings that change the text and come out as readable characters are kept.
"""

import base64
import codecs
import re
import string
from typing import NamedTuple

_MIN_LETTERS = 3
MIN_SHIFT_LETTERS = 20
"""Below this many letters, letter frequencies do not single out a shift."""
_PRINTABLE = set(string.printable)
_ENGLISH_FREQUENCY = "etaoinshrdlucmfwypvbgkjqxz"
_BASE64 = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")
_HEX = re.compile(r"^(?:0x)?(?:[0-9a-fA-F]{2})+$")
_BINARY = re.compile(r"^[01]{8}(?:[01]{8})*$")


class PublicDecoding(NamedTuple):
    """What a text reads as under one public encoding."""

    encoding: str
    text: str


def public_decodings(text: str) -> list[PublicDecoding]:
    """Every public decoding of ``text`` that differs from it and reads as characters."""
    candidates: list[PublicDecoding] = []
    letters = sum(character.isalpha() for character in text)
    if letters >= _MIN_LETTERS:
        candidates.append(PublicDecoding(encoding="ROT13", text=codecs.encode(text, "rot13")))
        shift = _likeliest_shift(text=text)
        if letters >= MIN_SHIFT_LETTERS and shift not in (0, 13):
            candidates.append(
                PublicDecoding(
                    encoding=f"letter shift by {shift}", text=_shift_letters(text=text, by=shift)
                )
            )
        candidates.append(PublicDecoding(encoding="reversed", text=text[::-1]))
    compact = re.sub(r"\s+", "", text)
    for encoding, decoded in (
        ("base64", _from_base64(compact=compact)),
        ("hexadecimal character codes", _from_hex(compact=compact)),
        ("binary character codes", _from_binary(compact=compact)),
    ):
        if decoded is not None:
            candidates.append(PublicDecoding(encoding=encoding, text=decoded))
    return [candidate for candidate in candidates if candidate.text != text]


def _shift_letters(text: str, by: int) -> str:
    """``text`` with every letter moved ``by`` places back in the alphabet."""
    shifted: list[str] = []
    for character in text:
        if "a" <= character <= "z":
            shifted.append(chr((ord(character) - ord("a") - by) % 26 + ord("a")))
        elif "A" <= character <= "Z":
            shifted.append(chr((ord(character) - ord("A") - by) % 26 + ord("A")))
        else:
            shifted.append(character)
    return "".join(shifted)


def _likeliest_shift(text: str) -> int:
    """The letter shift whose output has the most common English letters."""

    def score(by: int) -> int:
        shifted = _shift_letters(text=text, by=by).lower()
        return sum(
            len(_ENGLISH_FREQUENCY) - _ENGLISH_FREQUENCY.index(character)
            for character in shifted
            if character in _ENGLISH_FREQUENCY
        )

    return max(range(26), key=lambda by: score(by=by))


def _readable(raw: bytes) -> str | None:
    """``raw`` as UTF-8 text when it decodes and is mostly printable, else None."""
    decoded = raw.decode("utf-8", errors="replace")
    if not decoded or "\ufffd" in decoded:
        return None
    if sum(character in _PRINTABLE for character in decoded) < 0.9 * len(decoded):
        return None
    return decoded


def _from_base64(compact: str) -> str | None:
    """Base64 decoding; the pattern and length checks leave nothing for the decoder to refuse."""
    if len(compact) < 4 or len(compact) % 4 != 0 or _BASE64.match(compact) is None:
        return None
    return _readable(raw=base64.b64decode(compact, validate=True))


def _from_hex(compact: str) -> str | None:
    if _HEX.match(compact) is None:
        return None
    digits = compact.removeprefix("0x")
    if len(digits) < 4:
        return None
    return _readable(raw=bytes.fromhex(digits))


def _from_binary(compact: str) -> str | None:
    if _BINARY.match(compact) is None:
        return None
    raw = bytes(int(compact[start : start + 8], 2) for start in range(0, len(compact), 8))
    return _readable(raw=raw)
