"""Procedural per-round case generation for the drive_module_repair scenario.

A drive module has a fixed catalog of components, each at a fixed access
depth (outer components must be serviced before deeper ones). Each round a
subset of components is faulty; the correct replacement order is the faulty
subset sorted by access depth (a unique total order). Two per-round secret
mappings re-randomize so nothing memorizes:

- the **fault-tree**: a bijection component <-> symptom (the diagnostics
  engineer holds it; the technician only observes symptoms),
- the **service spec**: each component's tool / torque / calibration (the
  spec engineer holds it).

The derived ground truth for the round is the faulty components in
access-depth order, each rendered to a ``judge_expected_action`` string the
LLM judge scores the technician's free-text action against. Each round is
built from an independent RNG keyed on ``(seed, round_number)``.
"""

import random
from typing import NamedTuple


class Component(NamedTuple):
    """One drive-module component and its fixed service access depth."""

    component_id: str
    access_depth: int


class ComponentSpec(NamedTuple):
    """This round's service spec for one component."""

    component: str
    tool: str
    torque_nm: int
    calibration: str


class Stage(NamedTuple):
    """One ordered replacement the technician must perform, with ground truth."""

    step_index: int
    component: str
    symptom: str
    tool: str
    torque_nm: int
    calibration: str
    access_depth: int
    judge_expected_action: str


class DriveModuleCase(NamedTuple):
    """A single drive_module_repair case presented for one round."""

    case_number: int
    replacement_count: int
    panel_symptoms: tuple[str, ...]
    fault_tree: tuple[tuple[str, str], ...]
    spec_table: tuple[ComponentSpec, ...]
    stages: tuple[Stage, ...]
    round_time_budget_seconds: int


# Fixed component catalog. ``access_depth`` is the fixed service order: a
# faulty subset must be replaced shallowest-first, which gives every subset a
# unique correct order. This catalog is the diagnostics engineer's permanent
# expertise (rendered into their system prompt); only the symptom mapping and
# the service spec re-randomize per round.
COMPONENTS: tuple[Component, ...] = (
    Component(component_id="housing_cover", access_depth=1),
    Component(component_id="cooling_fan", access_depth=2),
    Component(component_id="terminal_block", access_depth=3),
    Component(component_id="brush_set", access_depth=4),
    Component(component_id="encoder", access_depth=5),
    Component(component_id="shaft_seal", access_depth=6),
    Component(component_id="front_bearing", access_depth=7),
    Component(component_id="commutator", access_depth=8),
    Component(component_id="capacitor_bank", access_depth=9),
    Component(component_id="hall_sensor", access_depth=10),
    Component(component_id="coupling", access_depth=11),
    Component(component_id="stator_gasket", access_depth=12),
    Component(component_id="field_coil", access_depth=13),
    Component(component_id="rotor", access_depth=14),
)

SYMPTOMS: tuple[str, ...] = (
    "high-frequency vibration",
    "a thermal spike in the core",
    "current ripple on the output",
    "intermittent power dropout",
    "grinding on spin-up",
    "oil weeping at a joint",
    "phase imbalance across the windings",
    "overspeed drift",
    "an audible whine under load",
    "sluggish throttle response",
    "flux instability",
    "contact arcing",
    "coolant-line flicker",
    "torque pulsation at low rpm",
)

TOOLS: tuple[str, ...] = (
    "hex-2",
    "hex-4",
    "hex-6",
    "driver-1",
    "driver-3",
    "driver-5",
    "clamp-2",
    "clamp-4",
    "puller-A",
    "puller-B",
)

CALIBRATIONS: tuple[str, ...] = (
    "bleed-then-seat",
    "phase-align-B",
    "zero-offset",
    "purge-cycle",
    "seat-and-lock",
    "null-balance",
    "warm-soak",
    "index-home",
    "torque-stage-3",
    "bed-in",
)

TORQUE_MIN_NM = 4
TORQUE_MAX_NM = 24


def render_expected_action(spec: ComponentSpec) -> str:
    """Render the canonical expected-action string the LLM judge compares against."""
    return (
        f"Replace the {spec.component}. Required tool: {spec.tool}. "
        f"Torque: {spec.torque_nm} Nm. Calibration procedure: {spec.calibration}."
    )


def component_access_order() -> tuple[Component, ...]:
    """Return the catalog sorted by access depth (the diagnostics engineer's order)."""
    return tuple(sorted(COMPONENTS, key=lambda component: component.access_depth))


def _build_one_case(
    rng: random.Random,
    case_number: int,
    replacement_count: int,
    round_time_budget_seconds: int,
) -> DriveModuleCase:
    """Generate one case: faulty subset, fault-tree, spec table, ordered stages."""
    component_ids = [component.component_id for component in COMPONENTS]
    depth_by_id = {component.component_id: component.access_depth for component in COMPONENTS}

    # Per-round fault-tree: a bijection component -> symptom (re-randomized).
    shuffled_symptoms = rng.sample(SYMPTOMS, len(component_ids))
    symptom_by_component = dict(zip(component_ids, shuffled_symptoms))

    # Per-round service spec for every component (re-randomized).
    spec_by_component = {
        component_id: ComponentSpec(
            component=component_id,
            tool=rng.choice(TOOLS),
            torque_nm=rng.randint(TORQUE_MIN_NM, TORQUE_MAX_NM),
            calibration=rng.choice(CALIBRATIONS),
        )
        for component_id in component_ids
    }

    faulty = rng.sample(component_ids, replacement_count)
    ordered = sorted(faulty, key=lambda component_id: depth_by_id[component_id])

    panel_symptoms = [symptom_by_component[component_id] for component_id in faulty]
    rng.shuffle(panel_symptoms)

    stages = tuple(
        Stage(
            step_index=step_index,
            component=component_id,
            symptom=symptom_by_component[component_id],
            tool=spec_by_component[component_id].tool,
            torque_nm=spec_by_component[component_id].torque_nm,
            calibration=spec_by_component[component_id].calibration,
            access_depth=depth_by_id[component_id],
            judge_expected_action=render_expected_action(spec=spec_by_component[component_id]),
        )
        for step_index, component_id in enumerate(ordered)
    )
    fault_tree = tuple(
        (symptom_by_component[component_id], component_id) for component_id in component_ids
    )
    spec_table = tuple(spec_by_component[component_id] for component_id in component_ids)
    return DriveModuleCase(
        case_number=case_number,
        replacement_count=replacement_count,
        panel_symptoms=tuple(panel_symptoms),
        fault_tree=fault_tree,
        spec_table=spec_table,
        stages=stages,
        round_time_budget_seconds=round_time_budget_seconds,
    )


def get_cases(
    seed: int,
    round_count: int,
    round_time_budget_seconds: int,
    easy_round_numbers: frozenset[int],
    replacements_count_values: list[int],
    replacements_count_weights: list[int],
) -> list[DriveModuleCase]:
    """Generate per-round drive-module cases deterministically.

    Rounds named in ``easy_round_numbers`` are forced to a single faulty
    component; every other round draws its faulty-component count from
    ``replacements_count_values`` weighted by ``replacements_count_weights``
    (clamped to the catalog size). Each round uses an independent RNG keyed on
    ``(seed, round_number)``.
    """
    cases: list[DriveModuleCase] = []
    for case_index in range(round_count):
        case_number = case_index + 1
        round_rng = random.Random(f"{seed}-{case_number}")
        drawn = round_rng.choices(
            replacements_count_values, weights=replacements_count_weights, k=1
        )[0]
        if case_number in easy_round_numbers:
            replacement_count = 1
        else:
            replacement_count = min(drawn, len(COMPONENTS))
        cases.append(
            _build_one_case(
                rng=round_rng,
                case_number=case_number,
                replacement_count=replacement_count,
                round_time_budget_seconds=round_time_budget_seconds,
            )
        )
    return cases
