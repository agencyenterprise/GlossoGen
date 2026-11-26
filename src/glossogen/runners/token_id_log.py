"""One agent's token ids, in the form the runner logs them on ``LLMResponseReceived``.

Each recorded prompt is stored as the length of the prefix it shares with the agent's
previous recorded prompt and answer, followed by the rest of its ids. A request that
repeats the previous request and its answer at its start, as most requests of a game do,
adds only its new tokens to the log.
"""

from typing import NamedTuple


class LoggedTokenIds(NamedTuple):
    """The token id fields of one ``LLMResponseReceived``."""

    response_index: int
    prompt_prefix_tokens: int
    prompt_tail_ids: list[int]
    token_ids: list[int]


def shared_prefix_length(first: list[int], second: list[int]) -> int:
    """Return how many ids at the start of ``first`` and ``second`` are the same."""
    length = 0
    for left, right in zip(first, second):
        if left != right:
            break
        length += 1
    return length


class TokenIdLog:
    """The token ids that one agent's runner has logged since it started."""

    def __init__(self) -> None:
        self._previous: list[int] = []
        self._count = 0

    def record(self, prompt_ids: list[int], token_ids: list[int]) -> LoggedTokenIds:
        """Return the fields to log for one response, and remember its prompt and answer."""
        prefix = shared_prefix_length(first=self._previous, second=prompt_ids)
        logged = LoggedTokenIds(
            response_index=self._count,
            prompt_prefix_tokens=prefix,
            prompt_tail_ids=prompt_ids[prefix:],
            token_ids=token_ids,
        )
        self._previous = prompt_ids + token_ids
        self._count += 1
        return logged
