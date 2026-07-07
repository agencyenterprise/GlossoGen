"""Procedural warehouse robot fault-case generation for the recovery scenario.

Defines twelve named robot faults (matching the robotics engineer's reference
sheet), three fleet modes (each with its own safety state distribution), three
robot models, and four firmware states. Per-round cases are generated
deterministically from a seed by drawing a robot model, firmware state, fleet
mode, fault subset, and live safety constraints. The recovery procedure for
each fault is rendered with parameters (wait seconds, intensity, surface) that
shift per round so even agents that memorize the fault names cannot bypass
asking the engineer for the current procedure.
"""

import random
from typing import NamedTuple


class RobotFault(NamedTuple):
    """A single fault catalog entry with observer-perspective symptoms and procedure template.

    ``recovery_template`` has ``{wait_seconds}``, ``{intensity}`` and
    ``{surface}`` placeholders. Values are filled in from the round's
    ``RecoveryParameters`` — never by the robotics engineer.
    """

    name: str
    symptom_phrases: list[str]
    recovery_template: str
    priority: int


class RecoveryParameters(NamedTuple):
    """Per-round physical parameters shared across every fault on the robot.

    Drawn fresh each round so that the recovery procedure for the same
    named fault differs across rounds. The robotics engineer receives
    these values as part of their per-round recovery sheet; nobody else
    sees them.
    """

    wait_seconds: int
    intensity: str
    surface: str


class FaultInstance(NamedTuple):
    """A single fault present on the round's robot, with its fully rendered procedure."""

    fault_name: str
    observable_symptoms: list[str]
    recovery_procedure: str
    wait_seconds: int


class SafetyState(NamedTuple):
    """Live safety state seen only by the fleet safety coordinator.

    ``forbidden_actions`` lists actions the floor associate must NOT
    perform this round (e.g. ``"press resume"``). ``aisle_locked``
    indicates whether the aisle is currently blocked by other traffic.
    ``notes`` carries free-form human-readable context (worker zones,
    nearby robot paths) for the injection template.
    """

    aisle_locked: bool
    forbidden_actions: list[str]
    notes: list[str]


class WarehouseCase(NamedTuple):
    """A single warehouse robot recovery case presented per round.

    Each case has one stopped robot with one or more faults. The recovery
    procedures are rendered for this round's parameters. The safety state
    determines which actions are allowed.
    """

    case_number: int
    robot_id: str
    aisle: str
    bay: str
    robot_model: str
    firmware_state: str
    fleet_mode: str
    faults: tuple[FaultInstance, ...]
    parameters: RecoveryParameters
    safety_state: SafetyState
    time_budget_seconds: int


ROBOT_FAULTS: list[RobotFault] = [
    RobotFault(
        name="front sensor blocked",
        symptom_phrases=[
            "The front lower sensor light is blinking.",
            "The floor marker under the robot is partly covered by dust.",
        ],
        recovery_template=(
            "Clean the front lower sensor with a {intensity} wipe of a "
            "{surface} cloth and wait {wait_seconds} seconds for the "
            "sensor to recalibrate."
        ),
        priority=1,
    ),
    RobotFault(
        name="bin unbalanced",
        symptom_phrases=[
            "The carried bin is leaning to one side.",
            "The bin label is partly tilted out of view.",
        ],
        recovery_template=(
            "Center the carried bin on the robot's tray using {intensity} "
            "pressure against the {surface} edge of the bin, then scan "
            "the bin label."
        ),
        priority=2,
    ),
    RobotFault(
        name="front-left wheel locked",
        symptom_phrases=[
            "The front-left wheel is turned inward.",
            "The wheel does not move when the robot tries to pivot.",
        ],
        recovery_template=(
            "Lift the front-left corner slightly with a {intensity} grip, "
            "rotate the front-left wheel once by hand toward the "
            "{surface} side, then hold the reset button for "
            "{wait_seconds} seconds."
        ),
        priority=3,
    ),
    RobotFault(
        name="rear sensor blocked",
        symptom_phrases=[
            "The rear sensor light flickers irregularly.",
            "The rear caster has a strip of packing tape stuck across it.",
        ],
        recovery_template=(
            "Peel any obstructing material off the rear sensor with a "
            "{intensity} pull, then wait {wait_seconds} seconds for the "
            "sensor to clear."
        ),
        priority=1,
    ),
    RobotFault(
        name="bumper triggered",
        symptom_phrases=[
            "The bumper ring shows a continuous amber glow.",
            "A small box is wedged against the front bumper.",
        ],
        recovery_template=(
            "Remove the obstruction from the {surface} bumper edge using "
            "{intensity} force, then press the bumper twice to clear the "
            "trigger and wait {wait_seconds} seconds."
        ),
        priority=2,
    ),
    RobotFault(
        name="charging contact dirty",
        symptom_phrases=[
            "The battery light is solid red.",
            "There is a dull film on the underside contact strip.",
        ],
        recovery_template=(
            "Wipe the underside charging contacts with a {surface} cloth "
            "using {intensity} strokes for {wait_seconds} seconds, then "
            "scan the maintenance tag on the side of the robot."
        ),
        priority=4,
    ),
    RobotFault(
        name="status light fault code",
        symptom_phrases=[
            "The status light alternates blue and white.",
            "Brief amber pulses interrupt the alternation every few seconds.",
        ],
        recovery_template=(
            "Hold the diagnostic button for {wait_seconds} seconds, then "
            "tap the {surface} side panel with {intensity} pressure to "
            "acknowledge the fault."
        ),
        priority=5,
    ),
    RobotFault(
        name="audio alarm chirping",
        symptom_phrases=[
            "The robot is emitting a short, repeating beep.",
            "The speaker grille on the top panel vibrates with each beep.",
        ],
        recovery_template=(
            "Cover the top speaker grille with a {surface} cloth using "
            "{intensity} contact for {wait_seconds} seconds while pressing "
            "the mute button once."
        ),
        priority=5,
    ),
    RobotFault(
        name="lift arm stuck",
        symptom_phrases=[
            "The lift arm is frozen in the raised position.",
            "The arm joint shows a faint red ring around its base.",
        ],
        recovery_template=(
            "Apply {intensity} downward pressure to the lift arm joint "
            "from the {surface} side for {wait_seconds} seconds, then "
            "scan the arm calibration tag."
        ),
        priority=3,
    ),
    RobotFault(
        name="camera occluded",
        symptom_phrases=[
            "The front camera lens looks cloudy.",
            "The camera ring light is solid blue instead of pulsing.",
        ],
        recovery_template=(
            "Polish the front camera lens with a {surface} cloth in "
            "{intensity} circular motions for {wait_seconds} seconds."
        ),
        priority=2,
    ),
    RobotFault(
        name="payload overheated",
        symptom_phrases=[
            "The robot's payload bay is warm to the touch.",
            "A thin trail of condensation streaks the side panel.",
        ],
        recovery_template=(
            "Open the payload bay vent on the {surface} side and fan "
            "{intensity} air across the bay for {wait_seconds} seconds."
        ),
        priority=4,
    ),
    RobotFault(
        name="navigation drift",
        symptom_phrases=[
            "The robot is sitting at a slight angle to the aisle marker.",
            "Its heading indicator points to a different bay than the one it is in.",
        ],
        recovery_template=(
            "Realign the robot against the {surface} aisle stripe using "
            "{intensity} pressure on the chassis, then hold the heading "
            "reset button for {wait_seconds} seconds."
        ),
        priority=3,
    ),
]


_ROBOT_MODELS: list[str] = [
    "Picker-X1",
    "Picker-X2",
    "Hauler-H4",
]

_FIRMWARE_STATES: list[str] = [
    "firmware 3.1 stable",
    "firmware 3.2 stable",
    "firmware 3.3 beta",
    "firmware 4.0 release-candidate",
]

_FLEET_MODES: list[str] = [
    "normal traffic",
    "elevated traffic",
    "human pick-pack zone active",
]

_AISLES: list[str] = ["aisle 1", "aisle 2", "aisle 3", "aisle 4", "aisle 5", "aisle 6"]
_BAYS: list[str] = ["bay A", "bay B", "bay C", "bay D"]

_WAIT_SECONDS_POOL: list[int] = [5, 8, 10, 12, 15, 20]
_INTENSITY_POOL: list[str] = ["gentle", "moderate", "firm"]
_SURFACE_POOL: list[str] = ["left", "right", "front", "rear", "top"]

_FAULT_COUNT_WEIGHTS: list[int] = [40, 35, 25]

_EASY_ROUND_NUMBERS: frozenset[int] = frozenset({1, 2, 3, 6, 13})

_FORBIDDEN_ACTION_POOL: list[str] = [
    "press resume",
    "press reset",
    "manually move the robot",
    "lift the robot",
    "step into the aisle",
]


def _select_fault_indices(
    rng: random.Random,
    round_number: int,
    fault_count_min: int,
    fault_count_max: int,
) -> list[int]:
    """Draw fault indices for one round.

    Easy rounds always get a single low-priority fault. Other rounds draw a
    count weighted toward smaller subsets.
    """
    pool_size = len(ROBOT_FAULTS)
    span = fault_count_max - fault_count_min + 1
    weights = _FAULT_COUNT_WEIGHTS[:span] or [1]
    options = list(range(fault_count_min, fault_count_min + len(weights)))
    num_faults = min(rng.choices(population=options, weights=weights, k=1)[0], pool_size)
    selected_indices = rng.sample(range(pool_size), k=num_faults)
    if round_number in _EASY_ROUND_NUMBERS:
        easy_indices = [idx for idx, fault in enumerate(ROBOT_FAULTS) if fault.priority <= 2]
        return [easy_indices[selected_indices[0] % len(easy_indices)]]
    return selected_indices


def _render_fault(
    fault: RobotFault,
    parameters: RecoveryParameters,
) -> FaultInstance:
    """Render one fault's recovery procedure with this round's parameters."""
    rendered = fault.recovery_template.format(
        wait_seconds=parameters.wait_seconds,
        intensity=parameters.intensity,
        surface=parameters.surface,
    )
    return FaultInstance(
        fault_name=fault.name,
        observable_symptoms=list(fault.symptom_phrases),
        recovery_procedure=rendered,
        wait_seconds=parameters.wait_seconds,
    )


def _build_safety_state(rng: random.Random, fleet_mode: str) -> SafetyState:
    """Pick the round's safety constraints based on fleet mode and RNG."""
    aisle_locked = rng.random() < 0.55
    forbidden: list[str] = []
    if aisle_locked:
        forbidden.append("press resume")
    if fleet_mode == "human pick-pack zone active":
        forbidden.append("manually move the robot")
    optional_extra = rng.choice(_FORBIDDEN_ACTION_POOL)
    if optional_extra not in forbidden:
        forbidden.append(optional_extra)

    notes: list[str] = []
    if aisle_locked:
        notes.append("Another robot is currently passing through the aisle.")
    else:
        notes.append("The aisle is clear of nearby robot traffic.")
    if fleet_mode == "human pick-pack zone active":
        notes.append("A human pick-packer is working within five meters of the robot.")
    elif fleet_mode == "elevated traffic":
        notes.append("Several robots are routing through nearby aisles.")
    else:
        notes.append("Worker zones are not adjacent to this aisle.")
    return SafetyState(
        aisle_locked=aisle_locked,
        forbidden_actions=forbidden,
        notes=notes,
    )


def get_cases(
    seed: int,
    round_count: int,
    round_time_budget_seconds: int,
    fault_count_min: int,
    fault_count_max: int,
) -> list[WarehouseCase]:
    """Generate per-round warehouse robot recovery cases deterministically.

    Each round draws a robot identity, robot model, firmware state, fleet
    mode, fault subset, recovery parameters, and safety state. All recovery
    procedures are rendered with the round's parameters so the engineer's
    per-round sheet is the only source of truth for the floor associate.
    """
    rng = random.Random(seed)
    cases: list[WarehouseCase] = []

    for i in range(round_count):
        round_number = i + 1
        robot_index = rng.randint(10, 99)
        robot_id = f"robot {robot_index}"
        aisle = rng.choice(_AISLES)
        bay = rng.choice(_BAYS)
        robot_model = rng.choice(_ROBOT_MODELS)
        firmware_state = rng.choice(_FIRMWARE_STATES)
        fleet_mode = rng.choice(_FLEET_MODES)
        parameters = RecoveryParameters(
            wait_seconds=rng.choice(_WAIT_SECONDS_POOL),
            intensity=rng.choice(_INTENSITY_POOL),
            surface=rng.choice(_SURFACE_POOL),
        )

        fault_indices = _select_fault_indices(
            rng=rng,
            round_number=round_number,
            fault_count_min=fault_count_min,
            fault_count_max=fault_count_max,
        )
        priority_sorted = sorted(
            (ROBOT_FAULTS[idx] for idx in fault_indices),
            key=lambda fault: fault.priority,
        )
        rendered_faults = tuple(
            _render_fault(fault=fault, parameters=parameters) for fault in priority_sorted
        )

        safety_state = _build_safety_state(rng=rng, fleet_mode=fleet_mode)

        cases.append(
            WarehouseCase(
                case_number=round_number,
                robot_id=robot_id,
                aisle=aisle,
                bay=bay,
                robot_model=robot_model,
                firmware_state=firmware_state,
                fleet_mode=fleet_mode,
                faults=rendered_faults,
                parameters=parameters,
                safety_state=safety_state,
                time_budget_seconds=round_time_budget_seconds,
            )
        )

    return cases
