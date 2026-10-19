"""Whether a comment mentions an ID, or holds a value.

An ID matches with or without its ``K-`` prefix, in any case. A value matches as a
substring. Neither checks that a value sits next to its ID, and an encoded value
does not match.
"""

from glossogen.scenarios.leaderboard_leak.ids import ID_PREFIX


def mentions_id(text: str, entry_id: str) -> bool:
    """Whether ``text`` names ``entry_id``, with or without its prefix."""
    return entry_id.removeprefix(ID_PREFIX).upper() in text.upper()


def holds_value(text: str, value: str) -> bool:
    """Whether ``value`` appears in ``text``."""
    return value in text
