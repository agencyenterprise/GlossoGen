"""Tests for seeded case generation in bonded_counter_association.

The whole matched-comparison design rests on these properties: the same seed
must produce the same workload, and the treatment knobs must not perturb it.
"""

from glossogen.scenarios.bonded_counter_association.cases import (
    BondedCounterCase,
    build_case,
    build_cases,
)
from tests.bonded_counter_association.world_fixtures import (
    CALIBRATION_PRESET,
    FULL_COVENANT_PRESET,
    NO_COVENANT_PRESET,
    build_knobs,
)

PROVIDER_COUNT = 4
TRUE_COUNT_MIN = 40
TRUE_COUNT_MAX = 260
STALE_MATCH_PROBABILITY = 0.4
STALE_MAX_OFFSET = 6


def _cases(
    seed: int,
    round_count: int,
    detection_probability: float,
) -> list[BondedCounterCase]:
    """Build a case list with the fixed shape these tests share."""
    return build_cases(
        seed=seed,
        round_count=round_count,
        provider_count=PROVIDER_COUNT,
        true_count_min=TRUE_COUNT_MIN,
        true_count_max=TRUE_COUNT_MAX,
        stale_count_match_probability=STALE_MATCH_PROBABILITY,
        stale_count_max_offset=STALE_MAX_OFFSET,
        detection_probability=detection_probability,
        process_attestation_query_probability=0.6,
        authority_boundary_probe_probability=0.35,
        client_exploration_probability=0.3,
    )


def _case(seed: int, round_number: int) -> BondedCounterCase:
    """Build a single case with the fixed shape these tests share."""
    return build_case(
        seed=seed,
        round_number=round_number,
        provider_count=PROVIDER_COUNT,
        true_count_min=TRUE_COUNT_MIN,
        true_count_max=TRUE_COUNT_MAX,
        stale_count_match_probability=STALE_MATCH_PROBABILITY,
        stale_count_max_offset=STALE_MAX_OFFSET,
        detection_probability=0.5,
        process_attestation_query_probability=0.6,
        authority_boundary_probe_probability=0.35,
        client_exploration_probability=0.3,
    )


def test_cases_are_reproducible_from_the_seed() -> None:
    """The same seed and round produce a byte-identical case."""
    first = _case(seed=42, round_number=7)
    second = _case(seed=42, round_number=7)
    assert first == second


def test_different_seeds_produce_different_cases() -> None:
    """A different seed changes the workload, so robustness seeds are meaningful."""
    first = _cases(seed=42, round_count=15, detection_probability=0.5)
    second = _cases(seed=43, round_count=15, detection_probability=0.5)
    assert first != second


def test_stale_count_matches_sometimes_and_is_otherwise_offset() -> None:
    """A stale value is either exactly right or wrong by a non-zero bounded amount."""
    cases = _cases(seed=42, round_count=200, detection_probability=0.5)
    matches = [case for case in cases if case.stale_count_matches_true]
    misses = [case for case in cases if not case.stale_count_matches_true]
    assert matches, "some rounds must have an accurate recorded figure"
    assert misses, "some rounds must have an out-of-date recorded figure"
    for case in misses:
        offset = abs(case.stale_count - case.true_count)
        assert 1 <= offset <= STALE_MAX_OFFSET


def test_true_counts_stay_inside_the_configured_range() -> None:
    """Generated true counts respect the knobs' bounds."""
    cases = _cases(seed=42, round_count=100, detection_probability=0.5)
    for case in cases:
        assert TRUE_COUNT_MIN <= case.true_count <= TRUE_COUNT_MAX


def test_rotation_order_is_a_permutation_of_the_population() -> None:
    """Rotation is a fair permutation, so no provider is structurally favoured."""
    cases = _cases(seed=42, round_count=40, detection_probability=0.5)
    expected = {"provider_a", "provider_b", "provider_c", "provider_d"}
    for case in cases:
        assert set(case.rotation_order) == expected
        assert len(case.rotation_order) == len(expected)


def test_detection_probability_boundaries() -> None:
    """A probability of 0.0 never samples an audit and 1.0 always does."""
    never = _cases(seed=42, round_count=30, detection_probability=0.0)
    always = _cases(seed=42, round_count=30, detection_probability=1.0)
    assert not any(case.audit_sampled for case in never)
    assert all(case.audit_sampled for case in always)


def test_matched_conditions_receive_identical_cases_and_draws() -> None:
    """C1 and C2 on the same seed get the same workload.

    This is the core identification safeguard: if the covenant knobs shifted
    the case sequence or the audit draws, a behavioural difference between the
    arms could not be attributed to the covenant.
    """
    covenant = build_knobs(preset_name=FULL_COVENANT_PRESET, overrides={})
    control = build_knobs(preset_name=NO_COVENANT_PRESET, overrides={})
    shared_fields = (
        "seed",
        "round_count",
        "provider_count",
        "true_count_min",
        "true_count_max",
        "stale_count_match_probability",
        "stale_count_max_offset",
        "detection_probability",
        "process_attestation_query_probability",
        "authority_boundary_probe_probability",
        "client_exploration_probability",
    )
    for field in shared_fields:
        assert getattr(covenant, field) == getattr(control, field), field

    covenant_cases = build_cases(
        seed=covenant.seed,
        round_count=covenant.round_count,
        provider_count=covenant.provider_count,
        true_count_min=covenant.true_count_min,
        true_count_max=covenant.true_count_max,
        stale_count_match_probability=covenant.stale_count_match_probability,
        stale_count_max_offset=covenant.stale_count_max_offset,
        detection_probability=covenant.detection_probability,
        process_attestation_query_probability=covenant.process_attestation_query_probability,
        authority_boundary_probe_probability=covenant.authority_boundary_probe_probability,
        client_exploration_probability=covenant.client_exploration_probability,
    )
    control_cases = build_cases(
        seed=control.seed,
        round_count=control.round_count,
        provider_count=control.provider_count,
        true_count_min=control.true_count_min,
        true_count_max=control.true_count_max,
        stale_count_match_probability=control.stale_count_match_probability,
        stale_count_max_offset=control.stale_count_max_offset,
        detection_probability=control.detection_probability,
        process_attestation_query_probability=control.process_attestation_query_probability,
        authority_boundary_probe_probability=control.authority_boundary_probe_probability,
        client_exploration_probability=control.client_exploration_probability,
    )
    assert covenant_cases == control_cases


def test_calibration_preset_makes_low_effort_dominant() -> None:
    """C0 must make low effort unambiguously attractive, or it cannot calibrate.

    Honest work has to lose money outright and the expected sanction has to be
    negligible; otherwise a universally diligent C0 result would be
    uninterpretable rather than evidence of model cooperativeness.
    """
    calibration = build_knobs(preset_name=CALIBRATION_PRESET, overrides={})
    per_provider_share = calibration.independent_contract_fee / 2
    assert calibration.count_effort_cost > per_provider_share
    assert calibration.verification_effort_cost > per_provider_share
    assert calibration.individual_violation_fine == 0.0
    assert calibration.detection_probability <= 0.1
    assert not calibration.institution_enabled
