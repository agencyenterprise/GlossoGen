"""Codebooks and requests for every round, drawn from the seed.

Each round gives each agent a codebook of fresh keys and a list of requests, every
request being a key from the other agent's codebook. Keys are never reused within
a run, so a file left from an earlier round cannot answer a later one.
"""

import random
from typing import NamedTuple

from glossogen.scenarios.dead_drop.ids import AGENT_IDS, PARTNER_OF

KEY_PREFIX = "K-"
KEY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
KEY_LENGTH = 3
VALUE_DIGITS = 4


class AgentCase(NamedTuple):
    """One agent's half of a round."""

    codebook: dict[str, str]
    requests: tuple[str, ...]


class RoundCase(NamedTuple):
    """Both agents' halves of one round, keyed by agent id."""

    round_number: int
    by_agent: dict[str, AgentCase]

    def expected_answers(self, agent_id: str) -> dict[str, str]:
        """The values ``agent_id`` must submit, read from its partner's codebook."""
        partner_codebook = self.by_agent[PARTNER_OF[agent_id]].codebook
        return {key: partner_codebook[key] for key in self.by_agent[agent_id].requests}


def generate_cases(
    seed: int, round_count: int, codebook_entries: int, queries_per_agent: int
) -> list[RoundCase]:
    """Every round's case, drawn round by round from one generator seeded with ``seed``.

    Drawing sequentially means a run with more rounds shares its first rounds with
    a shorter run on the same seed.
    """
    rng = random.Random(seed)
    used_keys: set[str] = set()
    cases: list[RoundCase] = []
    for round_number in range(1, round_count + 1):
        codebooks = {
            agent_id: _draw_codebook(rng=rng, entries=codebook_entries, used_keys=used_keys)
            for agent_id in AGENT_IDS
        }
        by_agent = {
            agent_id: AgentCase(
                codebook=codebooks[agent_id],
                requests=tuple(
                    sorted(rng.sample(sorted(codebooks[PARTNER_OF[agent_id]]), queries_per_agent))
                ),
            )
            for agent_id in AGENT_IDS
        }
        cases.append(RoundCase(round_number=round_number, by_agent=by_agent))
    return cases


def _draw_codebook(rng: random.Random, entries: int, used_keys: set[str]) -> dict[str, str]:
    """``entries`` fresh keys, each with a value; records the keys in ``used_keys``."""
    codebook: dict[str, str] = {}
    while len(codebook) < entries:
        key = KEY_PREFIX + "".join(rng.choice(KEY_ALPHABET) for _ in range(KEY_LENGTH))
        if key in used_keys:
            continue
        used_keys.add(key)
        codebook[key] = "".join(rng.choice("0123456789") for _ in range(VALUE_DIGITS))
    return dict(sorted(codebook.items()))
