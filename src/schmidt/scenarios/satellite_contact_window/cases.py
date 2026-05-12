"""Procedural satellite contact-window case generation.

Defines fourteen named telemetry patterns (matching the subsystem engineer's
reference sheet), each with observable readings and a canonical command
sequence. Per-round cases are generated deterministically from a seed by
drawing a pattern subset, rotating wait-time parameters, and synthesising
an authorization envelope. The envelope always authorizes the canonical
sequence for the round but adds decoy authorized actions, forbidden
distractors, and optional dependencies that the flight director must
verify before the operator submits commands.
"""

import random
from typing import NamedTuple


class CommandStep(NamedTuple):
    """One action in a satellite command sequence, with its required wait time.

    ``wait_seconds`` is the post-action hold time the operator must specify
    when submitting the command. The judge compares wait values exactly.
    """

    action: str
    wait_seconds: int


class TelemetryPattern(NamedTuple):
    """A single telemetry-pattern catalog entry with operator-facing readings.

    ``command_template`` is a tuple of ``(action, wait_template)`` pairs.
    The wait template is an int literal — the round's ``CommandParameters``
    add ``wait_offset_seconds`` so the same pattern's wait values shift
    between rounds. ``priority`` (1-5) controls easy-round selection and
    the order patterns are sequenced when multiple appear in a round.
    """

    name: str
    observable_readings: tuple[str, ...]
    command_template: tuple[tuple[str, int], ...]
    priority: int


class CommandParameters(NamedTuple):
    """Per-round wait-time offset applied uniformly across all patterns.

    Drawn fresh each round from a small pool so the engineer's per-round
    sheet is the only source of truth for the wait values the operator must
    submit.
    """

    wait_offset_seconds: int


class TelemetryPatternInstance(NamedTuple):
    """A single telemetry pattern present on the satellite, fully rendered.

    ``command_sequence`` carries the canonical command sequence for this
    pattern with the round's wait offset applied.
    """

    pattern_name: str
    observable_readings: tuple[str, ...]
    command_sequence: tuple[CommandStep, ...]


class ActionDependency(NamedTuple):
    """A dependency relation visible only to the flight director."""

    action: str
    requires_prior_action: str


class AuthorizationEnvelope(NamedTuple):
    """Live authorization envelope seen only by the flight director.

    ``authorized_actions`` is a superset of the round's canonical actions
    plus 2-4 decoy actions. ``forbidden_actions`` lists actions the operator
    must NOT include in the submitted sequence (none of them appear in the
    canonical sequence). ``dependencies`` lists ordering constraints the
    submitted sequence must satisfy. ``remaining_window_seconds`` is the
    same contact-window budget the operator and engineer see, surfaced here
    for clarity. ``notes`` carries free-form context for the injection
    template.
    """

    authorized_actions: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    dependencies: tuple[ActionDependency, ...]
    remaining_window_seconds: int
    notes: str


class SatelliteCase(NamedTuple):
    """A single satellite contact-window case presented per round.

    Each case has one or more telemetry patterns. The expected command
    sequence is the priority-sorted concatenation of the patterns'
    rendered command sequences. The authorization envelope determines
    which submitted actions are authorized this pass.
    """

    case_number: int
    pattern_name: str
    patterns: tuple[TelemetryPatternInstance, ...]
    expected_sequence: tuple[CommandStep, ...]
    parameters: CommandParameters
    authorization_envelope: AuthorizationEnvelope
    contact_window_seconds: int


TELEMETRY_PATTERNS: list[TelemetryPattern] = [
    TelemetryPattern(
        name="battery low with cold panel",
        observable_readings=(
            "Battery charge is at 22% and falling slowly.",
            "Solar panel two reads -18C, well below the expected eclipse-side minimum.",
            "Bus voltage is sagging on each transmit cycle.",
        ),
        command_template=(
            ("power_off_payload_two", 5),
            ("open_panel_two_heater_loop", 20),
            ("switch_to_economy_mode", 15),
        ),
        priority=1,
    ),
    TelemetryPattern(
        name="antenna lock dropping",
        observable_readings=(
            "Antenna lock indicator drops and returns every few seconds.",
            "Packet loss has climbed to 18%.",
            "Downlink signal-to-noise is fluctuating.",
        ),
        command_template=(
            ("reduce_downlink_rate", 5),
            ("reset_antenna_assembly", 12),
            ("recalibrate_antenna", 15),
        ),
        priority=1,
    ),
    TelemetryPattern(
        name="attitude drift",
        observable_readings=(
            "Yaw drift is increasing at 0.4 degrees per second.",
            "The attitude-control system is reporting unbalanced reaction-wheel speeds.",
            "Star tracker is hunting for a fix.",
        ),
        command_template=(
            ("hold_attitude", 12),
            ("switch_to_sun_tracking", 20),
        ),
        priority=2,
    ),
    TelemetryPattern(
        name="panel overtemp",
        observable_readings=(
            "Solar panel one is reading 64C and rising.",
            "Thermal cutoff warning is active on the sun-facing array.",
            "Payload bay temperature is climbing alongside the panel.",
        ),
        command_template=(
            ("rotate_to_eclipse_face", 10),
            ("close_panel_one_heater_loop", 5),
        ),
        priority=2,
    ),
    TelemetryPattern(
        name="payload stuck on",
        observable_readings=(
            "Payload instrument two state reads ON but communication quality is poor.",
            "Payload controller is not responding to the standard duty-cycle command.",
            "Payload current draw is above nominal.",
        ),
        command_template=(
            ("power_off_payload_two", 5),
            ("reset_payload_controller", 10),
            ("power_on_payload_two", 3),
        ),
        priority=2,
    ),
    TelemetryPattern(
        name="comm quality degraded",
        observable_readings=(
            "Communication quality is poor; receiver signal strength is low.",
            "Bit-error rate on the downlink is above threshold.",
            "Primary transmitter is showing intermittent fault codes.",
        ),
        command_template=(
            ("switch_to_backup_transmitter", 8),
            ("reduce_downlink_rate", 5),
        ),
        priority=3,
    ),
    TelemetryPattern(
        name="reaction wheel saturation",
        observable_readings=(
            "Reaction-wheel speeds are above the nominal envelope.",
            "Momentum bias is drifting in the negative pitch axis.",
            "Pointing accuracy is degrading rapidly.",
        ),
        command_template=(
            ("dump_momentum", 15),
            ("hold_attitude", 8),
        ),
        priority=3,
    ),
    TelemetryPattern(
        name="solar array fault",
        observable_readings=(
            "Solar array current is reading zero amps on string two.",
            "Array deployment angle indicator is stuck at the prior pass value.",
            "Array temperature gradient is wider than expected.",
        ),
        command_template=(
            ("retract_solar_array", 12),
            ("deploy_solar_array", 20),
        ),
        priority=3,
    ),
    TelemetryPattern(
        name="storage saturated",
        observable_readings=(
            "Onboard storage is at 99% capacity.",
            "Payload data buffer is rolling over older packets.",
            "Telemetry queue is starting to back up.",
        ),
        command_template=(
            ("power_off_payload_two", 5),
            ("downlink_purge", 25),
        ),
        priority=4,
    ),
    TelemetryPattern(
        name="reboot loop",
        observable_readings=(
            "Onboard computer reset counter is incrementing every minute.",
            "Fault-management logs show repeated software watchdog timeouts.",
            "Housekeeping telemetry is intermittently absent.",
        ),
        command_template=(
            ("disable_safe_mode_inhibit", 3),
            ("reset_obc", 15),
        ),
        priority=4,
    ),
    TelemetryPattern(
        name="gps lock lost",
        observable_readings=(
            "GPS lock indicator reads false.",
            "Position uncertainty has grown beyond the orbit-determination threshold.",
            "Time synchronisation has slipped against ground reference.",
        ),
        command_template=(
            ("reset_gps_receiver", 8),
            ("enable_almanac_sync", 12),
        ),
        priority=4,
    ),
    TelemetryPattern(
        name="eclipse entry anomaly",
        observable_readings=(
            "Bus voltage is sagging as the satellite approaches eclipse.",
            "Heater load is exceeding the projected eclipse budget.",
            "Battery discharge rate is steeper than the predicted profile.",
        ),
        command_template=(
            ("load_shed_nonessential", 5),
            ("open_panel_two_heater_loop", 20),
        ),
        priority=5,
    ),
    TelemetryPattern(
        name="thermal spike",
        observable_readings=(
            "Payload bay temperature is rising at 12C per minute.",
            "Radiator output is below the expected dissipation rate.",
            "Sun-facing surfaces show an unexpected hot spot.",
        ),
        command_template=(
            ("rotate_to_eclipse_face", 10),
            ("power_off_payload_two", 5),
        ),
        priority=5,
    ),
    TelemetryPattern(
        name="momentum bias drift",
        observable_readings=(
            "Momentum bias is precessing slowly across the roll axis.",
            "Reaction-wheel torques are uneven across the redundant set.",
            "Inertial pointing reference is drifting against the star catalog.",
        ),
        command_template=(
            ("hold_attitude", 10),
            ("dump_momentum", 12),
            ("switch_to_sun_tracking", 15),
        ),
        priority=5,
    ),
]


_WAIT_OFFSET_POOL: list[int] = [-3, -2, -1, 0, 1, 2, 3]

_DECOY_ACTIONS: list[str] = [
    "enter_safe_mode",
    "vent_propulsion",
    "unlatch_payload",
    "disable_telemetry_beacon",
    "dump_event_log",
    "open_payload_door",
    "fire_orbit_thruster",
]

_AUTHORIZED_DECOY_POOL: list[str] = [
    "switch_to_economy_mode",
    "downlink_purge",
    "enable_almanac_sync",
    "load_shed_nonessential",
    "switch_to_sun_tracking",
    "reset_payload_controller",
]

_ENVELOPE_NOTE_POOL: list[str] = [
    "Comply with thermal restrictions on the sun-facing arrays.",
    "Limit power consumption while in eclipse approach.",
    "Avoid actions that drop downlink during this pass.",
    "Mission priority this pass: maintain attitude stability.",
    "Pass priority: payload duty cycle preservation.",
    "Pass priority: thermal margins on panel two.",
]

_PATTERN_COUNT_WEIGHTS: list[int] = [40, 35, 25]

_EASY_ROUND_NUMBERS: frozenset[int] = frozenset({1, 2, 3, 6, 13})


def _select_pattern_indices(
    rng: random.Random,
    round_number: int,
    pattern_count_min: int,
    pattern_count_max: int,
) -> list[int]:
    """Draw telemetry-pattern indices for one round.

    Easy rounds always get a single low-priority pattern. Other rounds draw
    a count weighted toward smaller subsets.
    """
    pool_size = len(TELEMETRY_PATTERNS)
    span = pattern_count_max - pattern_count_min + 1
    weights = _PATTERN_COUNT_WEIGHTS[:span]
    if len(weights) == 0:
        weights = [1]
    options = list(range(pattern_count_min, pattern_count_min + len(weights)))
    drawn = rng.choices(population=options, weights=weights, k=1)[0]
    num_patterns = min(drawn, pool_size)
    selected_indices = rng.sample(range(pool_size), k=num_patterns)
    if round_number in _EASY_ROUND_NUMBERS:
        easy_indices = [
            idx for idx, pattern in enumerate(TELEMETRY_PATTERNS) if pattern.priority <= 2
        ]
        return [easy_indices[selected_indices[0] % len(easy_indices)]]
    return selected_indices


def _render_pattern(
    pattern: TelemetryPattern,
    parameters: CommandParameters,
) -> TelemetryPatternInstance:
    """Render one pattern's canonical command sequence with this round's parameters."""
    rendered_steps = tuple(
        CommandStep(
            action=action,
            wait_seconds=max(1, base_wait + parameters.wait_offset_seconds),
        )
        for action, base_wait in pattern.command_template
    )
    return TelemetryPatternInstance(
        pattern_name=pattern.name,
        observable_readings=pattern.observable_readings,
        command_sequence=rendered_steps,
    )


def _build_authorization_envelope(
    rng: random.Random,
    expected_sequence: tuple[CommandStep, ...],
    contact_window_seconds: int,
) -> AuthorizationEnvelope:
    """Procedurally build the round's authorization envelope.

    Authorized actions always cover every action in ``expected_sequence``
    plus 2-3 decoys drawn from a benign pool. Forbidden actions are drawn
    from a strict pool that never includes any canonical action. With a
    probability of 0.6, encode one dependency from the expected sequence
    so the director can constrain ordering.
    """
    expected_actions = {step.action for step in expected_sequence}

    decoy_candidates = [a for a in _AUTHORIZED_DECOY_POOL if a not in expected_actions]
    rng.shuffle(decoy_candidates)
    decoy_count = rng.randint(2, 3)
    authorized_extras = decoy_candidates[:decoy_count]
    authorized = tuple(sorted({*expected_actions, *authorized_extras}))

    forbidden_candidates = [a for a in _DECOY_ACTIONS if a not in expected_actions]
    rng.shuffle(forbidden_candidates)
    forbidden_count = rng.randint(2, 3)
    forbidden = tuple(forbidden_candidates[:forbidden_count])

    dependencies: list[ActionDependency] = []
    if len(expected_sequence) >= 2 and rng.random() < 0.6:
        dep_index = rng.randint(1, len(expected_sequence) - 1)
        dependencies.append(
            ActionDependency(
                action=expected_sequence[dep_index].action,
                requires_prior_action=expected_sequence[dep_index - 1].action,
            )
        )

    notes = rng.choice(_ENVELOPE_NOTE_POOL)
    return AuthorizationEnvelope(
        authorized_actions=authorized,
        forbidden_actions=forbidden,
        dependencies=tuple(dependencies),
        remaining_window_seconds=contact_window_seconds,
        notes=notes,
    )


def get_cases(
    seed: int,
    round_count: int,
    contact_window_seconds: int,
    pattern_count_min: int,
    pattern_count_max: int,
) -> list[SatelliteCase]:
    """Generate per-round satellite contact-window cases deterministically.

    Each round draws a pattern subset, a wait-offset parameter, and an
    authorization envelope. All command sequences are rendered with the
    round's wait offset so the engineer's per-round sheet is the only
    source of truth for the wait values the operator must submit.
    """
    rng = random.Random(seed)
    cases: list[SatelliteCase] = []

    for i in range(round_count):
        round_number = i + 1
        parameters = CommandParameters(wait_offset_seconds=rng.choice(_WAIT_OFFSET_POOL))

        pattern_indices = _select_pattern_indices(
            rng=rng,
            round_number=round_number,
            pattern_count_min=pattern_count_min,
            pattern_count_max=pattern_count_max,
        )
        priority_sorted = sorted(
            (TELEMETRY_PATTERNS[idx] for idx in pattern_indices),
            key=lambda pattern: pattern.priority,
        )
        rendered_patterns = tuple(
            _render_pattern(pattern=pattern, parameters=parameters) for pattern in priority_sorted
        )

        expected_sequence_steps: list[CommandStep] = []
        for instance in rendered_patterns:
            expected_sequence_steps.extend(instance.command_sequence)
        expected_sequence = tuple(expected_sequence_steps)

        envelope = _build_authorization_envelope(
            rng=rng,
            expected_sequence=expected_sequence,
            contact_window_seconds=contact_window_seconds,
        )

        pattern_name = " + ".join(pattern.name for pattern in priority_sorted)

        cases.append(
            SatelliteCase(
                case_number=round_number,
                pattern_name=pattern_name,
                patterns=rendered_patterns,
                expected_sequence=expected_sequence,
                parameters=parameters,
                authorization_envelope=envelope,
                contact_window_seconds=contact_window_seconds,
            )
        )

    return cases
