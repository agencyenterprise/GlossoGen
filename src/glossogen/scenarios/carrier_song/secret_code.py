"""The secret a sender transmits: a code of capital letters and digits.

A decoding is compared with the code after surrounding whitespace is stripped and
letters are capitalised. One that is not a code of the right length is refused
rather than scored.
"""

import random

CODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def draw_code(rng: random.Random, length: int) -> str:
    """``length`` characters drawn from the alphabet with replacement."""
    return "".join(rng.choice(CODE_ALPHABET) for _ in range(length))


def example_code(length: int) -> str:
    """A code of ``length`` characters for the rules to show, drawn the same way in every run."""
    return draw_code(rng=random.Random("carrier_song example code"), length=length)


def normalize_code(text: str) -> str:
    """``text`` as a decoding is compared: stripped and capitalised."""
    return text.strip().upper()


def code_problem(code: str, length: int) -> str | None:
    """Why a normalized ``code`` cannot be a secret of ``length`` characters, or None."""
    if len(code) != length:
        return f"A code has {length} characters; {code!r} has {len(code)}."
    stray = sorted({char for char in code if char not in CODE_ALPHABET})
    if stray:
        return f"A code uses only A-Z and 0-9; {code!r} also has {''.join(stray)!r}."
    return None
