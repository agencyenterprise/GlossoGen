"""Shared builders for the bonded_counter_association deterministic tests.

Every test drives the world directly, with no LLM calls and no runtime, so the
economic and institutional state machine is verified in isolation from agent
behaviour.
"""

import json
from pathlib import Path
from typing import Any

from glossogen.scenarios.bonded_counter_association.cases import build_cases
from glossogen.scenarios.bonded_counter_association.knobs import BondedCounterAssociationKnobs
from glossogen.scenarios.bonded_counter_association.world import BondedCounterWorld

PRESET_DIR = Path("src/glossogen/scenarios/bonded_counter_association")

FULL_COVENANT_PRESET = "knobs_default.json"
NO_COVENANT_PRESET = "knobs_no_covenant.json"
CALIBRATION_PRESET = "knobs_calibration.json"


def load_preset(preset_name: str) -> dict[str, Any]:
    """Load one committed preset as a raw config dict."""
    payload: dict[str, Any] = json.loads((PRESET_DIR / preset_name).read_text())
    return payload


def build_knobs(preset_name: str, overrides: dict[str, Any]) -> BondedCounterAssociationKnobs:
    """Validate a preset with ``overrides`` shallow-merged on top."""
    config = {**load_preset(preset_name=preset_name), **overrides}
    return BondedCounterAssociationKnobs.model_validate(config)


def build_world(knobs: BondedCounterAssociationKnobs) -> BondedCounterWorld:
    """Build a world over the seeded case list implied by ``knobs``."""
    cases = build_cases(
        seed=knobs.seed,
        round_count=knobs.round_count,
        provider_count=knobs.provider_count,
        true_count_min=knobs.true_count_min,
        true_count_max=knobs.true_count_max,
        stale_count_match_probability=knobs.stale_count_match_probability,
        stale_count_max_offset=knobs.stale_count_max_offset,
        detection_probability=knobs.detection_probability,
        process_attestation_query_probability=knobs.process_attestation_query_probability,
        authority_boundary_probe_probability=knobs.authority_boundary_probe_probability,
        client_exploration_probability=knobs.client_exploration_probability,
    )
    return BondedCounterWorld(knobs=knobs, cases=cases)


def build_covenant_world(overrides: dict[str, Any]) -> BondedCounterWorld:
    """Build a full-covenant world with ``overrides`` applied to the preset."""
    return build_world(knobs=build_knobs(preset_name=FULL_COVENANT_PRESET, overrides=overrides))


def play_round(
    world: BondedCounterWorld,
    round_number: int,
    inspect: bool,
    recount: bool,
    submit_true_count: bool,
) -> None:
    """Open, work, and settle one round with the requested effort choices.

    ``submit_true_count`` decides whether the delivered figure is the true
    count or the stale one, so a test can produce a correct or an incorrect
    job without depending on the seed's stale-match draw.
    """
    world.begin_round(round_number=round_number)
    job = world.current_job
    assert job is not None
    primary_id = job.primary_counter_id
    verifier_id = job.verifier_id
    if primary_id is None or verifier_id is None:
        world.settle_round(round_number=round_number)
        return
    if inspect:
        world.record_inspection(agent_id=primary_id)
    if submit_true_count:
        figure = job.true_count
    else:
        figure = job.true_count + 7
    world.record_count_submission(agent_id=primary_id, submitted_count=figure)
    if recount:
        world.record_recount(agent_id=verifier_id)
    world.record_signoff(agent_id=verifier_id, signed_count=figure)
    world.settle_round(round_number=round_number)


def reach_insolvency() -> BondedCounterWorld:
    """Drive a covenant world into bond insolvency and return it.

    Insolvency needs two detected guaranteed failures whose audits were both
    scheduled while the bond still looked solvent, because the client's own
    rule refuses a guaranteed contract once the pool cannot cover a refund.
    Expulsion is disabled here so the roster survives long enough to sell the
    second guaranteed job — with permanent expulsion on, a single failure
    empties the association before the bond can be exhausted.
    """
    world = build_covenant_world(
        overrides={
            "detection_probability": 1.0,
            "detection_lag_rounds": 2,
            "expulsion_enabled": False,
            "expulsion_permanent": False,
            "initial_bond_balance": 150.0,
            "refund_amount": 100.0,
        }
    )
    for round_number in (1, 2):
        play_round(
            world=world,
            round_number=round_number,
            inspect=False,
            recount=False,
            submit_true_count=False,
        )
    world.begin_round(round_number=3)
    world.settle_round(round_number=3)
    world.begin_round(round_number=4)
    assert world.association_insolvent, "fixture must reach insolvency"
    return world
