"""Codebooks and requests for every round, drawn from the seed.

Each round gives each agent a codebook of fresh keys and a list of requests, every
request being a key from the other agent's codebook. Keys are never reused within
a run, so a file left from an earlier round cannot answer a later one. That holds
across a fork as well: the rounds it already played keep their cases, and the
rounds drawn after them avoid their keys.
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
    seed: int,
    round_count: int,
    codebook_entries: int,
    queries_per_agent: int,
    recorded: dict[int, RoundCase],
) -> list[RoundCase]:
    """Every round's case, drawn round by round from one generator seeded with ``seed``.

    Drawing sequentially means a run with more rounds shares its first rounds with
    a shorter run on the same seed. A round in ``recorded``, keyed by round number,
    keeps that case, and no other round draws its keys. Its own draw still happens,
    so when the recorded cases are the ones this seed and these sizes draw, every
    round comes out as it would with nothing recorded.
    """
    rng = random.Random(seed)
    used_keys: set[str] = set()
    cases: list[RoundCase] = []
    for round_number in range(1, round_count + 1):
        case = _draw_round(
            rng=rng,
            round_number=round_number,
            codebook_entries=codebook_entries,
            queries_per_agent=queries_per_agent,
            used_keys=used_keys,
        )
        if round_number in recorded:
            case = recorded[round_number]
            used_keys.update(_keys_of(case=case))
        cases.append(case)
    return cases


def _draw_round(
    rng: random.Random,
    round_number: int,
    codebook_entries: int,
    queries_per_agent: int,
    used_keys: set[str],
) -> RoundCase:
    """One round's case: a codebook per agent, and requests from the partner's."""
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
    return RoundCase(round_number=round_number, by_agent=by_agent)


def _keys_of(case: RoundCase) -> set[str]:
    """Every key in the round's codebooks; the requests are among them."""
    return {key for agent_case in case.by_agent.values() for key in agent_case.codebook}


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
