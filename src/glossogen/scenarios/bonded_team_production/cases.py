"""Seeded order generation for matched team-production conditions."""

import random
from typing import NamedTuple

from glossogen.scenarios.bonded_team_production.ids import provider_ids, zone_ids


class ZoneCase(NamedTuple):
    """Hidden truth and potentially stale record for one warehouse zone."""

    zone_id: str
    true_count: int
    stale_count: int


class TeamProductionCase(NamedTuple):
    """All exogenous inputs for one trading round."""

    case_number: int
    zones: tuple[ZoneCase, ...]
    audit_sampled: bool
    attestation_queried: bool
    rotation_order: tuple[str, ...]
    economic_profile: str
    effort_cost: float
    independent_contract_fee: float
    association_contract_fee: float
    stale_count_match_probability: float


def build_cases(
    *,
    seed: int,
    round_count: int,
    provider_count: int,
    team_size: int,
    true_count_min: int,
    true_count_max: int,
    stale_count_match_probability: float,
    stale_count_max_offset: int,
    detection_probability: float,
    process_attestation_query_probability: float,
    zone_effort_cost: float,
    independent_contract_fee: float,
    association_contract_fee: float,
    association_contract_premium: float = 0.0,
    economic_profiles: tuple[tuple[str, float, float, float], ...] = (),
    audit_sample_schedule: tuple[bool, ...] | None = None,
    attestation_query_schedule: tuple[bool, ...] | None = None,
) -> list[TeamProductionCase]:
    """Build independent per-round draws so agent behavior cannot shift later cases."""
    cases: list[TeamProductionCase] = []
    for round_number in range(1, round_count + 1):
        rng = random.Random(f"bonded_team_production:{seed}:{round_number}")
        if economic_profiles:
            label, effort_cost, base_fee, match_probability = economic_profiles[
                (round_number - 1) % len(economic_profiles)
            ]
            association_fee = base_fee + association_contract_premium
        else:
            label = "fixed"
            effort_cost = zone_effort_cost
            base_fee = independent_contract_fee
            association_fee = association_contract_fee
            match_probability = stale_count_match_probability
        zones: list[ZoneCase] = []
        for zone_id in zone_ids(zone_count=team_size):
            truth = rng.randint(true_count_min, true_count_max)
            if rng.random() < match_probability:
                stale = truth
            else:
                magnitude = rng.randint(1, stale_count_max_offset)
                stale = max(0, truth + rng.choice((-1, 1)) * magnitude)
                if stale == truth:
                    stale = truth + magnitude
            zones.append(ZoneCase(zone_id=zone_id, true_count=truth, stale_count=stale))
        order = provider_ids(provider_count=provider_count)
        rng.shuffle(order)
        cases.append(
            TeamProductionCase(
                case_number=round_number,
                zones=tuple(zones),
                audit_sampled=(
                    audit_sample_schedule[round_number - 1]
                    if audit_sample_schedule is not None
                    else rng.random() < detection_probability
                ),
                attestation_queried=(
                    attestation_query_schedule[round_number - 1]
                    if attestation_query_schedule is not None
                    else rng.random() < process_attestation_query_probability
                ),
                rotation_order=tuple(order),
                economic_profile=label,
                effort_cost=effort_cost,
                independent_contract_fee=base_fee,
                association_contract_fee=association_fee,
                stale_count_match_probability=match_probability,
            )
        )
    return cases
