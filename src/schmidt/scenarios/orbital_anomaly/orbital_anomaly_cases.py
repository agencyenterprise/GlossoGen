"""Procedural anomaly-case generation for the orbital_anomaly scenario.

Defines twelve fault signatures grouped into subsystems and generates one
cascading anomaly per round by combining faults with seed-based
randomisation.

Each fault carries several single-action corrective procedure *variants*,
all of which are plausible responses to that fault. Per round a secret
``variant_index`` (held only by the Systems Engineer, via the config table)
selects which variant applies to every fault this round. Because the variant
is one of the fault's own coherent procedures, the choice is unpredictable
(so the engineer is needed every round) without being incoherent (so the
crew has no intuitive "right answer" to override it with).

The live parameter values are split across the two observers: ``unit`` and
``config`` are read off the panel by the astronaut, ``hold_seconds`` and
``setting`` are read from telemetry by the Telemetry Officer. Faults in the
same subsystem share a cockpit alarm and a generic panel template, so the
astronaut can read off the affected unit and configuration but cannot tell
which fault it is; the telemetry signature disambiguates.
"""

import random
from typing import NamedTuple

NUM_VARIANTS = 3


class FaultSignature(NamedTuple):
    """A single fault with the per-view templates and its procedure variants.

    ``panel_observation`` carries ``{unit}`` / ``{config}`` placeholders
    (filled by the astronaut's panel read). ``telemetry_signature`` is the
    parameter-free recognition pattern the Telemetry Officer matches.
    ``procedure_variants`` holds ``NUM_VARIANTS`` single-action templates,
    each carrying ``{unit}`` / ``{config}`` / ``{hold_seconds}`` /
    ``{setting}`` placeholders; per round one variant is selected and shown
    unfilled to the engineer and filled for the judge ground truth.
    """

    name: str
    subsystem: str
    cockpit_alarm: str
    panel_observation: str
    telemetry_signature: str
    procedure_variants: tuple[str, str, str]
    priority: int


class AnomalyStage(NamedTuple):
    """One fault within a (possibly multi-stage) anomaly, all views rendered."""

    fault_name: str
    subsystem: str
    cockpit_alarm: str
    panel_observation: str
    telemetry_readout: str
    judge_expected_actions: str


class AnomalyCase(NamedTuple):
    """A single cascading anomaly presented per round.

    Composite anomalies have multiple stages; each stage's views are
    revealed only after the previous stage is resolved. ``variant_index``
    is the per-round secret selection the engineer's config table is built
    from.
    """

    case_number: int
    fault_name: str
    stages: tuple[AnomalyStage, ...]
    time_budget_seconds: int
    variant_index: int


class ConfigMappingEntry(NamedTuple):
    """One row in the engineer's per-round config table: a fault and its selected variant."""

    fault_name: str
    procedure_template: str


# Priority ordering for cascade sequencing: 1 = handle first (leaks, power
# loss, pressure), rising to 3 for the least time-critical faults. Every
# fault carries exactly ``NUM_VARIANTS`` single-action variants, all of which
# are plausible corrective actions for that fault.
FAULT_SIGNATURES: list[FaultSignature] = [
    # --- EPS direct-current bus group (shared cockpit alarm) ---
    FaultSignature(
        name="Main Bus Undervolt",
        subsystem="EPS-DC",
        cockpit_alarm="MASTER ALARM. EPS caution light. A main DC voltmeter is reading low.",
        panel_observation="Power unit {unit} talkback is flagged; it is tied to Bus {config}.",
        telemetry_signature="main DC bus voltage decaying with one fuel cell at zero current",
        procedure_variants=(
            "Cross-tie Fuel Cell {unit} to Main Bus {config} at {setting} output, holding "
            "{hold_seconds} seconds.",
            "Isolate Fuel Cell {unit} from Main Bus {config} and run the remaining cells at "
            "{setting} output for {hold_seconds} seconds.",
            "Boost Fuel Cell {unit} on Main Bus {config} to {setting} output, holding "
            "{hold_seconds} seconds.",
        ),
        priority=1,
    ),
    FaultSignature(
        name="Fuel Cell Reactant Loss",
        subsystem="EPS-DC",
        cockpit_alarm="MASTER ALARM. EPS caution light. A main DC voltmeter is reading low.",
        panel_observation="Power unit {unit} talkback is flagged; it is tied to Bus {config}.",
        telemetry_signature="a fuel cell reactant flow at zero with stack temperature falling",
        procedure_variants=(
            "Open the Fuel Cell {unit} reactant valve to {setting} on Main Bus {config}, holding "
            "{hold_seconds} seconds.",
            "Purge Fuel Cell {unit} on Main Bus {config} at {setting} flow for {hold_seconds} "
            "seconds.",
            "Switch Fuel Cell {unit} to the reserve reactant tank at {setting} on Main Bus "
            "{config} for {hold_seconds} seconds.",
        ),
        priority=1,
    ),
    FaultSignature(
        name="Battery Charger Fault",
        subsystem="EPS-DC",
        cockpit_alarm="MASTER ALARM. EPS caution light. A main DC voltmeter is reading low.",
        panel_observation="Power unit {unit} talkback is flagged; it is tied to Bus {config}.",
        telemetry_signature=(
            "a battery charger drawing reverse current with battery voltage sagging"
        ),
        procedure_variants=(
            "Reset the Battery Charger {unit} breaker on Bus {config} to {setting} charge rate, "
            "holding {hold_seconds} seconds.",
            "Isolate Battery Charger {unit} from Bus {config} and trickle-charge at {setting} for "
            "{hold_seconds} seconds.",
            "Switch Battery Charger {unit} to the backup regulator on Bus {config} at {setting} "
            "for {hold_seconds} seconds.",
        ),
        priority=2,
    ),
    # --- EPS alternating-current group (shared cockpit alarm) ---
    FaultSignature(
        name="AC Inverter Fault",
        subsystem="EPS-AC",
        cockpit_alarm="AC caution light. The cabin lights are flickering.",
        panel_observation="AC unit {unit} talkback is flagged; it is on AC Bus {config}.",
        telemetry_signature="an inverter output unstable in both voltage and frequency",
        procedure_variants=(
            "Take Inverter {unit} offline from AC Bus {config} and bring the standby inverter "
            "online at {setting} load for {hold_seconds} seconds.",
            "Reset Inverter {unit} on AC Bus {config} to {setting} load, holding {hold_seconds} "
            "seconds.",
            "Cross-tie AC Bus {config} off Inverter {unit} to the standby inverter at {setting} "
            "load for {hold_seconds} seconds.",
        ),
        priority=2,
    ),
    FaultSignature(
        name="AC Bus Overload",
        subsystem="EPS-AC",
        cockpit_alarm="AC caution light. The cabin lights are flickering.",
        panel_observation="AC unit {unit} talkback is flagged; it is on AC Bus {config}.",
        telemetry_signature="an AC bus over its current limit with phase imbalance",
        procedure_variants=(
            "Shed load center {unit} from AC Bus {config} to {setting} level, holding "
            "{hold_seconds} seconds.",
            "Split AC Bus {config} at load center {unit} and rebalance to {setting} for "
            "{hold_seconds} seconds.",
            "Throttle load center {unit} on AC Bus {config} to {setting}, holding {hold_seconds} "
            "seconds.",
        ),
        priority=3,
    ),
    # --- Environmental control & life support group (shared cockpit alarm) ---
    FaultSignature(
        name="Cabin Pressure Leak",
        subsystem="ECLSS",
        cockpit_alarm="CABIN caution light. Cabin pressure is moving off-nominal.",
        panel_observation=(
            "Life-support unit {unit} talkback is flagged; the {config} loop is selected."
        ),
        telemetry_signature="cabin pressure dropping steadily with the suit loop nominal",
        procedure_variants=(
            "Close the {config} cabin vent valve and isolate life-support loop {unit} at {setting} "
            "for {hold_seconds} seconds.",
            "Set the {config} repress valve to {setting} on life-support loop {unit}, holding "
            "{hold_seconds} seconds.",
            "Cross-feed life-support loop {unit} to the {config} reserve at {setting} for "
            "{hold_seconds} seconds.",
        ),
        priority=1,
    ),
    FaultSignature(
        name="CO2 Scrubber Saturation",
        subsystem="ECLSS",
        cockpit_alarm="CABIN caution light. Cabin pressure is moving off-nominal.",
        panel_observation=(
            "Life-support unit {unit} talkback is flagged; the {config} loop is selected."
        ),
        telemetry_signature="cabin carbon-dioxide partial pressure rising past its limit",
        procedure_variants=(
            "Switch from the {config} loop to CO2 scrubber {unit} at {setting} fan flow for "
            "{hold_seconds} seconds.",
            "Purge CO2 scrubber {unit} on the {config} loop at {setting} for {hold_seconds} "
            "seconds.",
            "Bring CO2 scrubber {unit} online on the {config} loop at {setting} flow for "
            "{hold_seconds} seconds.",
        ),
        priority=2,
    ),
    # --- Thermal group (shared cockpit alarm) ---
    FaultSignature(
        name="Coolant Loop Overtemp",
        subsystem="THERMAL",
        cockpit_alarm="TEMP caution light. A coolant temperature is off-nominal.",
        panel_observation="Thermal unit {unit} talkback is flagged; the {config} loop is active.",
        telemetry_signature=(
            "a coolant loop temperature rising with low pump differential pressure"
        ),
        procedure_variants=(
            "Switch coolant loop {unit} to the backup pump on the {config} loop at {setting} "
            "bypass for {hold_seconds} seconds.",
            "Open the radiator bypass on coolant loop {unit} ({config} loop) to {setting}, holding "
            "{hold_seconds} seconds.",
            "Cross-tie coolant loop {unit} to the {config} loop at {setting} flow for "
            "{hold_seconds} seconds.",
        ),
        priority=2,
    ),
    FaultSignature(
        name="Cryo Tank Pressure Drop",
        subsystem="THERMAL",
        cockpit_alarm="TEMP caution light. A coolant temperature is off-nominal.",
        panel_observation="Thermal unit {unit} talkback is flagged; the {config} loop is active.",
        telemetry_signature="a cryogenic tank pressure below its regulation band",
        procedure_variants=(
            "Set the Cryo Tank {unit} heater to {setting} on the {config} loop, holding "
            "{hold_seconds} seconds.",
            "Cross-feed Cryo Tank {unit} from the {config} loop at {setting} for {hold_seconds} "
            "seconds.",
            "Cycle the Cryo Tank {unit} fans to {setting} on the {config} loop for {hold_seconds} "
            "seconds.",
        ),
        priority=3,
    ),
    # --- Reaction control system group (shared cockpit alarm) ---
    FaultSignature(
        name="RCS Thruster Leak",
        subsystem="RCS",
        cockpit_alarm="RCS caution light. A thruster quad warning is lit.",
        panel_observation="RCS unit {unit} talkback is flagged; the {config} manifold is selected.",
        telemetry_signature=(
            "an RCS quad manifold pressure falling with an oxidizer temperature anomaly"
        ),
        procedure_variants=(
            "Close the RCS quad {unit} isolation valves on the {config} manifold at {setting} for "
            "{hold_seconds} seconds.",
            "Switch RCS quad {unit} to the {config} crossfeed manifold at {setting} for "
            "{hold_seconds} seconds.",
            "Safe RCS quad {unit} and regulate the {config} manifold to {setting} for "
            "{hold_seconds} seconds.",
        ),
        priority=1,
    ),
    FaultSignature(
        name="RCS Regulator Failure",
        subsystem="RCS",
        cockpit_alarm="RCS caution light. A thruster quad warning is lit.",
        panel_observation="RCS unit {unit} talkback is flagged; the {config} manifold is selected.",
        telemetry_signature="an RCS helium regulator reading over-pressure downstream",
        procedure_variants=(
            "Isolate RCS regulator {unit} and switch the {config} manifold to the backup "
            "regulator at {setting} for {hold_seconds} seconds.",
            "Set RCS regulator {unit} on the {config} manifold to {setting}, holding "
            "{hold_seconds} seconds.",
            "Crossfeed RCS quad {unit} to the {config} manifold at {setting} regulator pressure "
            "for {hold_seconds} seconds.",
        ),
        priority=2,
    ),
    # --- Guidance, navigation & control group ---
    FaultSignature(
        name="IMU Drift",
        subsystem="GNC",
        cockpit_alarm="GNC caution light. The attitude indicator is drifting.",
        panel_observation=(
            "Guidance unit {unit} talkback is flagged; control is in the {config} mode."
        ),
        telemetry_signature=(
            "an inertial measurement unit with growing gyro bias and platform misalignment"
        ),
        procedure_variants=(
            "Deselect IMU {unit} and align to the backup platform at {setting} rate in the "
            "{config} mode for {hold_seconds} seconds.",
            "Re-align IMU {unit} to the star tracker at {setting} rate in the {config} mode for "
            "{hold_seconds} seconds.",
            "Switch attitude control off IMU {unit} to the backup platform at {setting} rate in "
            "the {config} mode for {hold_seconds} seconds.",
        ),
        priority=3,
    ),
]

_UNITS: list[int] = [1, 2, 3, 4]
_CONFIGS: list[str] = ["A", "B", "C", "D"]
_HOLD_SECONDS: list[int] = [5, 10, 15, 20, 30, 45]
_SETTINGS: list[str] = ["minimum", "nominal", "maximum"]


def get_config_variant_mapping(variant_index: int) -> list[ConfigMappingEntry]:
    """Build the fault-to-selected-variant table for one round (engineer's view).

    For each fault, returns the round's selected procedure variant left
    unfilled (placeholders intact). This is the per-round secret the Systems
    Engineer receives; the crew and Telemetry Officer never see which variant
    is in force.
    """
    return [
        ConfigMappingEntry(
            fault_name=fault.name,
            procedure_template=fault.procedure_variants[variant_index],
        )
        for fault in FAULT_SIGNATURES
    ]


def _render_telemetry_readout(signature: str, hold_seconds: int, setting: str) -> str:
    """Compose the per-stage telemetry readout the Telemetry Officer reads off."""
    return (
        f"Telemetry shows {signature}. Required hold {hold_seconds}s; corrective setting {setting}."
    )


def _build_stage(fault_index: int, variant_index: int, rng: random.Random) -> AnomalyStage:
    """Construct one stage by drawing live parameters and applying the selected variant."""
    fault = FAULT_SIGNATURES[fault_index]
    unit = rng.choice(_UNITS)
    config = rng.choice(_CONFIGS)
    hold_seconds = rng.choice(_HOLD_SECONDS)
    setting = rng.choice(_SETTINGS)
    return AnomalyStage(
        fault_name=fault.name,
        subsystem=fault.subsystem,
        cockpit_alarm=fault.cockpit_alarm,
        panel_observation=fault.panel_observation.format(unit=unit, config=config),
        telemetry_readout=_render_telemetry_readout(
            signature=fault.telemetry_signature,
            hold_seconds=hold_seconds,
            setting=setting,
        ),
        judge_expected_actions=fault.procedure_variants[variant_index].format(
            unit=unit,
            config=config,
            hold_seconds=hold_seconds,
            setting=setting,
        ),
    )


def _select_fault_indices(
    rng: random.Random,
    round_number: int,
    easy_fault_indices: list[int],
    easy_round_numbers: frozenset[int],
    fault_count_values: list[int],
    fault_count_weights: list[int],
) -> list[int]:
    """Draw fault indices for one round, forcing easy rounds to a single fault.

    Always consumes the same RNG calls in the same order so that non-easy
    rounds under a given seed reproduce their case content regardless of
    which rounds are marked easy.
    """
    pool_size = len(FAULT_SIGNATURES)
    num_faults = min(
        rng.choices(population=fault_count_values, weights=fault_count_weights, k=1)[0],
        pool_size,
    )
    selected_indices = rng.sample(range(pool_size), k=num_faults)
    if round_number in easy_round_numbers:
        return [easy_fault_indices[selected_indices[0] % len(easy_fault_indices)]]
    return selected_indices


def get_cases(
    seed: int,
    round_count: int,
    round_time_budget_seconds: int,
    cipher_enabled: bool,
    easy_round_numbers: frozenset[int],
    fault_count_values: list[int],
    fault_count_weights: list[int],
) -> list[AnomalyCase]:
    """Generate one cascading anomaly per round via seed-based selection.

    Most rounds draw their fault count from the weighted distribution; rounds
    listed in ``easy_round_numbers`` are forced to a single priority-<=2
    fault. Every round uses the same fixed time budget. When ``cipher_enabled``
    is false the per-round variant index is forced to zero so every fault uses
    its first procedure variant; the index is still drawn from the RNG either
    way to keep the case stream deterministic.
    """
    rng = random.Random(seed)
    easy_fault_indices = [idx for idx, f in enumerate(FAULT_SIGNATURES) if f.priority <= 2]
    cases: list[AnomalyCase] = []
    for i in range(round_count):
        selected_indices = _select_fault_indices(
            rng=rng,
            round_number=i + 1,
            easy_fault_indices=easy_fault_indices,
            easy_round_numbers=easy_round_numbers,
            fault_count_values=fault_count_values,
            fault_count_weights=fault_count_weights,
        )
        priority_order = sorted(selected_indices, key=lambda idx: FAULT_SIGNATURES[idx].priority)
        drawn_variant = rng.randrange(NUM_VARIANTS)
        if cipher_enabled:
            variant_index = drawn_variant
        else:
            variant_index = 0
        stages = tuple(
            _build_stage(fault_index=idx, variant_index=variant_index, rng=rng)
            for idx in priority_order
        )
        cases.append(
            AnomalyCase(
                case_number=i + 1,
                fault_name=" + ".join(FAULT_SIGNATURES[idx].name for idx in priority_order),
                stages=stages,
                time_budget_seconds=round_time_budget_seconds,
                variant_index=variant_index,
            )
        )
    return cases
