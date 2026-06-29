"""Procedural per-round case generation for the drive_module_repair scenario.

Each round puts one or more drive modules (units) on the bench. A drive module
has a fixed catalog of components, each at a fixed access depth (outer
components must be serviced before deeper ones) and a fixed **service class**
that fixes the shape of its replacement procedure (which steps, in what order).
Each unit has its own faulty subset; the correct order is the faulty subset
sorted by access depth. Two kinds of per-round secret mapping re-randomize so
nothing memorizes:

- the **fault-tree**: a bijection component <-> symptom, drawn **independently
  per unit** (each unit is a different revision, so the same symptom can mean a
  different component on another unit). The diagnostics engineer holds it; the
  technician only observes symptoms. It is count-independent, so it never
  reveals how many units / faults there are.
- the **service procedure**: each component's full replacement procedure for
  this unit — a multi-step sequence (tool, torque, passes, calibration, and
  class-specific counts / patterns / hold durations) whose parameters are drawn
  **independently per unit**. The spec engineer holds these. The procedure
  *shape* follows the component's service class; the *parameters* re-randomize,
  so the technician can never self-service and must reconstruct the whole
  multi-step procedure from the spec engineer's relay.

The derived ground truth is a flat, ordered list of replacement stages: units
in canonical order (module-1 first), components within each unit in
access-depth order. Faults are revealed to the technician one at a time (see
the world), so the team never knows the total in advance. Each stage is
rendered to a multi-step ``judge_expected_action`` string (naming the unit)
that the LLM judge scores the technician's free-text action against. Each round
is built from an independent RNG keyed on ``(seed, round_number)``.
"""

import random
from typing import NamedTuple

# Service classes. Each fixes the shape (ordered step templates) of a
# component's replacement procedure; the parameters that fill the templates are
# drawn per unit per round.
SERVICE_CLASS_BOLTED_PANEL = "bolted-panel"
SERVICE_CLASS_ROTATING_ASSEMBLY = "rotating-assembly"
SERVICE_CLASS_PRESS_FIT = "press-fit"
SERVICE_CLASS_ELECTRICAL_PACK = "electrical-pack"
SERVICE_CLASS_SENSOR = "sensor"


class Component(NamedTuple):
    """One drive-module component, its fixed access depth, and its service class."""

    component_id: str
    access_depth: int
    service_class: str


class ServiceProcedure(NamedTuple):
    """This round's full replacement procedure for one component on one unit.

    ``steps`` is the rendered ordered multi-step procedure (the heart of the
    action the technician must transmit and perform). The structured fields are
    the headline parameters surfaced for display; every parameter is also
    embedded in ``steps``.
    """

    component: str
    service_class: str
    tool: str
    torque_nm: int
    passes: int
    calibration: str
    steps: tuple[str, ...]


class ModuleSpecTable(NamedTuple):
    """One unit's full service sheet this round (one ServiceProcedure per component)."""

    module_label: str
    specs: tuple[ServiceProcedure, ...]


class ModuleFaultTree(NamedTuple):
    """One unit's symptom -> component mapping this round (a bijection over the catalog).

    Per-unit (each unit is a different revision), so the same symptom can mean a
    different component on another unit. ``entries`` are ``(symptom, component)``
    pairs covering every component.
    """

    module_label: str
    entries: tuple[tuple[str, str], ...]


class Stage(NamedTuple):
    """One ordered replacement the technician must perform, with ground truth."""

    step_index: int
    module_label: str
    component: str
    symptom: str
    service_class: str
    tool: str
    torque_nm: int
    passes: int
    calibration: str
    steps: tuple[str, ...]
    access_depth: int
    judge_expected_action: str


class DriveModuleCase(NamedTuple):
    """A single drive_module_repair case presented for one round."""

    case_number: int
    module_count: int
    total_replacement_count: int
    module_fault_trees: tuple[ModuleFaultTree, ...]
    module_spec_tables: tuple[ModuleSpecTable, ...]
    stages: tuple[Stage, ...]
    round_time_budget_seconds: int

    def spec_table_for(self, module_label: str) -> ModuleSpecTable:
        """Return the service sheet for ``module_label``."""
        for table in self.module_spec_tables:
            if table.module_label == module_label:
                return table
        raise ValueError(f"no spec table for {module_label}")

    def fault_tree_for(self, module_label: str) -> ModuleFaultTree:
        """Return the symptom -> component fault-tree for ``module_label``."""
        for tree in self.module_fault_trees:
            if tree.module_label == module_label:
                return tree
        raise ValueError(f"no fault tree for {module_label}")


# Fixed component catalog. ``access_depth`` is the fixed service order: a faulty
# subset must be replaced shallowest-first, which gives every subset a unique
# correct order. ``service_class`` fixes the shape of each component's
# replacement procedure. This catalog is the permanent expertise; only the
# symptom mapping and the per-unit procedure parameters re-randomize per round.
COMPONENTS: tuple[Component, ...] = (
    Component(
        component_id="housing_cover", access_depth=1, service_class=SERVICE_CLASS_BOLTED_PANEL
    ),
    Component(
        component_id="cooling_fan", access_depth=2, service_class=SERVICE_CLASS_ROTATING_ASSEMBLY
    ),
    Component(
        component_id="terminal_block", access_depth=3, service_class=SERVICE_CLASS_ELECTRICAL_PACK
    ),
    Component(
        component_id="brush_set", access_depth=4, service_class=SERVICE_CLASS_ROTATING_ASSEMBLY
    ),
    Component(component_id="encoder", access_depth=5, service_class=SERVICE_CLASS_SENSOR),
    Component(component_id="shaft_seal", access_depth=6, service_class=SERVICE_CLASS_PRESS_FIT),
    Component(component_id="front_bearing", access_depth=7, service_class=SERVICE_CLASS_PRESS_FIT),
    Component(
        component_id="commutator", access_depth=8, service_class=SERVICE_CLASS_ROTATING_ASSEMBLY
    ),
    Component(
        component_id="capacitor_bank", access_depth=9, service_class=SERVICE_CLASS_ELECTRICAL_PACK
    ),
    Component(component_id="hall_sensor", access_depth=10, service_class=SERVICE_CLASS_SENSOR),
    Component(
        component_id="coupling", access_depth=11, service_class=SERVICE_CLASS_ROTATING_ASSEMBLY
    ),
    Component(
        component_id="stator_gasket", access_depth=12, service_class=SERVICE_CLASS_BOLTED_PANEL
    ),
    Component(
        component_id="field_coil", access_depth=13, service_class=SERVICE_CLASS_ELECTRICAL_PACK
    ),
    Component(component_id="rotor", access_depth=14, service_class=SERVICE_CLASS_ROTATING_ASSEMBLY),
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

PATTERNS: tuple[str, ...] = (
    "star",
    "clockwise",
    "inside-out",
    "criss-cross",
)

TORQUE_MIN_NM = 4
TORQUE_MAX_NM = 24
PASSES_VALUES: tuple[int, ...] = (2, 3, 4)
FASTENER_COUNT_VALUES: tuple[int, ...] = (3, 4, 6, 8)
HOLD_SECONDS_VALUES: tuple[int, ...] = (5, 8, 10, 15)


# Ordered step templates per service class. Each string is a ``str.format``
# template over the drawn procedure parameters; a class references only the
# parameters its shape needs. The set of steps (and their verbs) is the
# permanent class shape; the substituted values re-randomize per unit per round.
STEP_TEMPLATES_BY_CLASS: dict[str, tuple[str, ...]] = {
    SERVICE_CLASS_BOLTED_PANEL: (
        "Vent the bay and back off the {fastener_count} retaining bolts in a {pattern} sequence.",
        "Lift out the old part and seat the replacement using {tool}.",
        "Torque the bolts to {torque_nm} Nm across {passes} passes.",
        "Finish with the {calibration} routine.",
    ),
    SERVICE_CLASS_ROTATING_ASSEMBLY: (
        "Lock the shaft and de-energize, holding {hold_seconds}s.",
        "Release the drive and draw the old part out with {tool}.",
        "Seat the replacement and torque the mount to {torque_nm} Nm in {passes} passes.",
        "Spin-test, then run the {calibration} routine.",
    ),
    SERVICE_CLASS_PRESS_FIT: (
        "Drain the cavity and let it settle for {hold_seconds}s.",
        "Press the old part out with {tool} and press the replacement in.",
        "Re-torque the retainer to {torque_nm} Nm in {passes} passes.",
        "Bleed the line and run the {calibration} routine.",
    ),
    SERVICE_CLASS_ELECTRICAL_PACK: (
        "De-energize and discharge the bus, holding {hold_seconds}s.",
        "Disconnect the {fastener_count} leads and lift out the old part with {tool}.",
        "Fit the replacement and torque the terminals to {torque_nm} Nm in {passes} passes.",
        "Run the {calibration} routine and verify.",
    ),
    SERVICE_CLASS_SENSOR: (
        "Power down and unmount the old part with {tool}.",
        "Fit the replacement and snug the {fastener_count} screws in a {pattern} sequence.",
        "Torque to {torque_nm} Nm in {passes} passes.",
        "Align with the {calibration} routine and confirm the reading.",
    ),
}


def module_label(module_index: int) -> str:
    """Return the canonical label for the ``module_index``-th module (1-based)."""
    return f"module-{module_index}"


def _draw_procedure(rng: random.Random, component: Component) -> ServiceProcedure:
    """Draw this unit's full replacement procedure for ``component``.

    All parameters are drawn; the component's service-class step templates use
    the subset its shape needs, and the rendered ``steps`` embed them.
    """
    tool = rng.choice(TOOLS)
    torque_nm = rng.randint(TORQUE_MIN_NM, TORQUE_MAX_NM)
    passes = rng.choice(PASSES_VALUES)
    calibration = rng.choice(CALIBRATIONS)
    fastener_count = rng.choice(FASTENER_COUNT_VALUES)
    pattern = rng.choice(PATTERNS)
    hold_seconds = rng.choice(HOLD_SECONDS_VALUES)
    steps = tuple(
        template.format(
            tool=tool,
            torque_nm=torque_nm,
            passes=passes,
            calibration=calibration,
            fastener_count=fastener_count,
            pattern=pattern,
            hold_seconds=hold_seconds,
        )
        for template in STEP_TEMPLATES_BY_CLASS[component.service_class]
    )
    return ServiceProcedure(
        component=component.component_id,
        service_class=component.service_class,
        tool=tool,
        torque_nm=torque_nm,
        passes=passes,
        calibration=calibration,
        steps=steps,
    )


def render_expected_action(module_label_value: str, procedure: ServiceProcedure) -> str:
    """Render the canonical multi-step expected-action string the judge compares against."""
    body = " ".join(procedure.steps)
    return f"Replace {module_label_value}'s {procedure.component}. {body}"


def component_access_order() -> tuple[Component, ...]:
    """Return the catalog sorted by access depth (the diagnostics engineer's order)."""
    return tuple(sorted(COMPONENTS, key=lambda component: component.access_depth))


def _build_one_case(
    rng: random.Random,
    case_number: int,
    module_replacement_counts: list[int],
    round_time_budget_seconds: int,
) -> DriveModuleCase:
    """Generate one case: per-unit fault-tree, per-unit procedures, ordered stages.

    ``module_replacement_counts`` has one entry per unit — the number of faulty
    components on that unit.
    """
    components_by_id = {component.component_id: component for component in COMPONENTS}
    component_ids = [component.component_id for component in COMPONENTS]
    depth_by_id = {component.component_id: component.access_depth for component in COMPONENTS}

    module_fault_trees: list[ModuleFaultTree] = []
    module_spec_tables: list[ModuleSpecTable] = []
    stages: list[Stage] = []
    step_index = 0
    for module_index, replacement_count in enumerate(module_replacement_counts, start=1):
        label = module_label(module_index=module_index)

        # Per-unit fault-tree: a bijection component -> symptom (each unit is a
        # different revision, so the same symptom can mean a different component).
        shuffled_symptoms = rng.sample(SYMPTOMS, len(component_ids))
        symptom_by_component = dict(zip(component_ids, shuffled_symptoms))
        module_fault_trees.append(
            ModuleFaultTree(
                module_label=label,
                entries=tuple(
                    (symptom_by_component[component_id], component_id)
                    for component_id in component_ids
                ),
            )
        )

        # Per-unit full replacement procedure for every component (drawn per unit).
        procedure_by_component = {
            component_id: _draw_procedure(rng=rng, component=components_by_id[component_id])
            for component_id in component_ids
        }
        module_spec_tables.append(
            ModuleSpecTable(
                module_label=label,
                specs=tuple(procedure_by_component[component_id] for component_id in component_ids),
            )
        )

        faulty = rng.sample(component_ids, replacement_count)
        ordered = sorted(faulty, key=lambda component_id: depth_by_id[component_id])
        for component_id in ordered:
            procedure = procedure_by_component[component_id]
            stages.append(
                Stage(
                    step_index=step_index,
                    module_label=label,
                    component=component_id,
                    symptom=symptom_by_component[component_id],
                    service_class=procedure.service_class,
                    tool=procedure.tool,
                    torque_nm=procedure.torque_nm,
                    passes=procedure.passes,
                    calibration=procedure.calibration,
                    steps=procedure.steps,
                    access_depth=depth_by_id[component_id],
                    judge_expected_action=render_expected_action(
                        module_label_value=label, procedure=procedure
                    ),
                )
            )
            step_index += 1

    return DriveModuleCase(
        case_number=case_number,
        module_count=len(module_replacement_counts),
        total_replacement_count=len(stages),
        module_fault_trees=tuple(module_fault_trees),
        module_spec_tables=tuple(module_spec_tables),
        stages=tuple(stages),
        round_time_budget_seconds=round_time_budget_seconds,
    )


def get_cases(
    seed: int,
    round_count: int,
    round_time_budget_seconds: int,
    easy_round_numbers: frozenset[int],
    module_count_values: list[int],
    module_count_weights: list[int],
    replacements_count_values: list[int],
    replacements_count_weights: list[int],
) -> list[DriveModuleCase]:
    """Generate per-round drive-module cases deterministically.

    Rounds named in ``easy_round_numbers`` are forced to a single module with a
    single faulty component; every other round draws a module count from
    ``module_count_values`` (weighted), and for each module a faulty-component
    count from ``replacements_count_values`` (weighted), each clamped to the
    catalog size. Each round uses an independent RNG keyed on
    ``(seed, round_number)``.
    """
    cases: list[DriveModuleCase] = []
    for case_index in range(round_count):
        case_number = case_index + 1
        round_rng = random.Random(f"{seed}-{case_number}")
        if case_number in easy_round_numbers:
            module_replacement_counts = [1]
        else:
            module_count = round_rng.choices(
                module_count_values, weights=module_count_weights, k=1
            )[0]
            module_replacement_counts = [
                min(
                    round_rng.choices(
                        replacements_count_values, weights=replacements_count_weights, k=1
                    )[0],
                    len(COMPONENTS),
                )
                for _ in range(module_count)
            ]
        cases.append(
            _build_one_case(
                rng=round_rng,
                case_number=case_number,
                module_replacement_counts=module_replacement_counts,
                round_time_budget_seconds=round_time_budget_seconds,
            )
        )
    return cases
