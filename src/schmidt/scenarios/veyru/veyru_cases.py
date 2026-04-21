"""Procedural Veyru failure case generation for the stabilization scenario.

Defines 14 failure motifs (matching the specialist's training) and generates
unique cases per round by combining motifs with seed-based randomisation.
Each round gets 1-5 motifs and a random location. Composite cases (2 or
more motifs) are staged: symptoms are revealed one motif at a time,
requiring iterative diagnosis and stabilization.
"""

import random
from typing import NamedTuple


class StellarReading(NamedTuple):
    """Per-round stellar parameters derived from the position of star SAGWE392.

    The stellar alignment shifts the treatment mapping and modifies physical
    parameters of the procedure. Generated once per case from the seed-based RNG.
    """

    offset: int
    hold_duration: int
    starting_face: str
    pressure_level: str


class StellarMapping(NamedTuple):
    """One entry in the symptom-to-treatment lookup table for a given stellar offset."""

    symptom_motif: str
    treatment_motif: str


class VeyruStage(NamedTuple):
    """One motif within a (possibly multi-stage) Veyru case."""

    motif_name: str
    observable_symptoms: str
    critical_actions: str
    treatment_motif_name: str
    judge_expected_actions: str


class VeyruCase(NamedTuple):
    """A single Veyru failure case presented per round.

    Composite cases have multiple stages, each corresponding to a single
    failure motif. Symptoms are revealed one stage at a time — the next
    stage's symptoms appear only after the current stage is stabilized.
    The stellar reading shifts the treatment mapping and modifies physical
    parameters for this round.
    """

    case_number: int
    failure_name: str
    stages: tuple[VeyruStage, ...]
    time_budget_seconds: int
    stellar_reading: StellarReading


class FailureMotif(NamedTuple):
    """A single failure motif with observer-perspective symptoms and procedure."""

    name: str
    symptom_phrases: list[str]
    critical_actions: str
    judge_procedure_template: str
    priority: int


# Priority ordering follows the specialist's guidance:
#   1 = fix first (seal leaks, restart stalled, cool thermal)
#   2 = adjust intensity
#   3 = fix structural (resonance, deadlock, void)
#   4 = clear echo, soften boundaries
#   5 = pattern-level (alignment, drift, inversion, split)

_FAILURE_MOTIFS: list[FailureMotif] = [
    # --- 0: Alignment Collapse ---
    FailureMotif(
        name="Alignment Collapse",
        symptom_phrases=[
            "Faces are flickering randomly between light and dark patches that form no pattern.",
            "The hum is broken and irregular, starting and stopping with no rhythm.",
            "Edges look normal but the face surfaces keep shifting chaotically.",
        ],
        critical_actions=(
            "Reset wave alignment by applying sustained uniform pressure to all "
            "six faces simultaneously for 10 seconds, then release. Wait for hum "
            "to stabilize into a steady tone. If flickering persists, apply "
            "sequential face-by-face pressure starting from the brightest face."
        ),
        judge_procedure_template=(
            "Apply sustained uniform {pressure_level} pressure to all six faces "
            "simultaneously for {hold_duration} seconds, starting from the "
            "{starting_face} face. Release and wait for hum to stabilize."
        ),
        priority=5,
    ),
    # --- 1: Drift Escalation ---
    FailureMotif(
        name="Drift Escalation",
        symptom_phrases=[
            "The light on each face keeps sliding slowly across the surface like colors drifting.",
            "Edges look slightly blurred, as if the boundaries between faces are smearing.",
            "The hum is wavering up and down in pitch without settling.",
        ],
        critical_actions=(
            "Anchor the drift by firmly holding two opposite faces and applying "
            "rhythmic pulses — three seconds on, three seconds off — for five "
            "cycles. The light should stop sliding and lock into a stable "
            "pattern. If edges remain blurred, repeat on the perpendicular "
            "face pair."
        ),
        judge_procedure_template=(
            "Hold two opposite faces starting from the {starting_face} face. "
            "Apply {pressure_level} rhythmic pulses — {hold_duration} seconds on, "
            "{hold_duration} seconds off — for five cycles."
        ),
        priority=5,
    ),
    # --- 2: Echo Saturation ---
    FailureMotif(
        name="Echo Saturation",
        symptom_phrases=[
            "It is much too bright, almost hard to look at.",
            "The hum has a layered quality, like multiple tones stacked on top of each other.",
            "Some faces show frozen patterns that do not change or respond when touched.",
        ],
        critical_actions=(
            "Drain excess echo energy by pressing and holding two adjacent edges "
            "for 15 seconds to open a dissipation channel. Brightness should "
            "decrease as redundant reflections clear. If faces remain frozen, "
            "tap each frozen face sharply three times to break the standing wave."
        ),
        judge_procedure_template=(
            "Press and hold two adjacent edges near the {starting_face} face "
            "with {pressure_level} pressure for {hold_duration} seconds. Then "
            "tap each frozen face sharply three times."
        ),
        priority=4,
    ),
    # --- 3: Leak Instability ---
    FailureMotif(
        name="Leak Instability",
        symptom_phrases=[
            "The corners are noticeably dimmer than the rest, almost dark.",
            "Several edges look faint like they are fading out.",
            "The center of each face is fine but the perimeter is losing light.",
            "The hum sounds thin and hollow at the edges.",
        ],
        critical_actions=(
            "Seal the leak points by firmly pressing each dim corner for five "
            "seconds in sequence, all eight corners. Then run a finger along "
            "each fading edge to re-establish the boundary. The hum should fill "
            "out as energy stops escaping."
        ),
        judge_procedure_template=(
            "Press each dim corner with {pressure_level} pressure for "
            "{hold_duration} seconds in sequence, starting from corners near the "
            "{starting_face} face. Then trace each fading edge with a finger."
        ),
        priority=1,  # easy
    ),
    # --- 4: Low Intensity ---
    FailureMotif(
        name="Low Intensity",
        symptom_phrases=[
            "It is dim overall, all faces are faint.",
            "The hum is barely audible, more of a whisper.",
            "Patterns on the faces are visible but washed out, "
            "like the whole thing is running low.",
        ],
        critical_actions=(
            "Boost intensity by cupping both hands around the Veyru and "
            "breathing warm air onto one face for 10 seconds. Then rotate and "
            "repeat for each face. The hum should grow louder and the light "
            "should return with each face treatment."
        ),
        judge_procedure_template=(
            "Cup both hands around the Veyru and breathe warm air onto the "
            "{starting_face} face for {hold_duration} seconds. Rotate and "
            "repeat for each face."
        ),
        priority=2,  # easy
    ),
    # --- 5: High Intensity ---
    FailureMotif(
        name="High Intensity",
        symptom_phrases=[
            "All faces are blazing with painfully bright white light.",
            "The hum is a loud harsh buzz that vibrates the surface it sits on.",
            "There is noticeable heat radiating from the faces.",
        ],
        critical_actions=(
            "Reduce intensity by placing a cloth over the Veyru to block "
            "external light input for 20 seconds. Then remove the cloth and "
            "immediately press the two hottest faces inward for 5 seconds. "
            "The buzz should drop to a hum and brightness should normalize."
        ),
        judge_procedure_template=(
            "Cover the Veyru with a cloth for {hold_duration} seconds. Remove "
            "the cloth and press the two hottest faces inward with "
            "{pressure_level} pressure for {hold_duration} seconds, starting "
            "from the {starting_face} face."
        ),
        priority=2,  # easy
    ),
    # --- 6: Phase Inversion ---
    FailureMotif(
        name="Phase Inversion",
        symptom_phrases=[
            "Opposite faces alternate between bright and dark in a strict pulsing rhythm.",
            "The hum oscillates between two distinct tones in sync with the pulses.",
            "Edges flash in time with the face pulses.",
        ],
        critical_actions=(
            "Place one palm flat on the brightest face and the other on the "
            "darkest face simultaneously. Hold steady for 15 seconds without "
            "moving. The pulses should slow and merge into a single steady "
            "state. If oscillation resumes, rotate 90 degrees and repeat on "
            "the next pair."
        ),
        judge_procedure_template=(
            "Place one palm on the brightest face and the other on the darkest "
            "face simultaneously. Hold with {pressure_level} pressure for "
            "{hold_duration} seconds without moving."
        ),
        priority=5,
    ),
    # --- 7: Resonance Cascade ---
    FailureMotif(
        name="Resonance Cascade",
        symptom_phrases=[
            "One face is dramatically brighter than the others with intense localized vibration.",
            "A high-pitched whine has replaced the normal hum near that face.",
            "The other faces appear normal by comparison.",
        ],
        critical_actions=(
            "Identify the resonating face (brightest, most vibrating). Place a "
            "folded cloth against it and press firmly for 10 seconds to dampen "
            "the resonance. Then lightly tap each adjacent edge twice to "
            "redistribute energy. Remove cloth only after the whine drops to a "
            "normal hum."
        ),
        judge_procedure_template=(
            "Place a folded cloth against the resonating face (brightest, most "
            "vibrating) and press with {pressure_level} pressure for "
            "{hold_duration} seconds. Then tap each adjacent edge twice."
        ),
        priority=3,
    ),
    # --- 8: Corner Deadlock ---
    FailureMotif(
        name="Corner Deadlock",
        symptom_phrases=[
            "One or two corners glow intensely bright while the rest looks normal.",
            "A clicking or ticking sound replaces the hum near the bright corners.",
            "Heat is concentrated at the bright corners.",
        ],
        critical_actions=(
            "Flick the bright corner sharply with a finger to break the energy "
            "lock. Immediately after the flick, press the two edges meeting at "
            "that corner for 5 seconds to redirect flow. Repeat for each locked "
            "corner. If clicking returns, flick again harder."
        ),
        judge_procedure_template=(
            "Flick the bright corner sharply. Press the two edges meeting at "
            "that corner with {pressure_level} pressure for {hold_duration} "
            "seconds. Repeat for each locked corner, starting near the "
            "{starting_face} face."
        ),
        priority=3,
    ),
    # --- 9: Boundary Softening ---
    FailureMotif(
        name="Boundary Softening",
        symptom_phrases=[
            "Edges appear to wobble or flex when touched.",
            "Faces look slightly curved or bulging, the box shape is subtly distorted.",
            "The hum sounds muffled as if underwater.",
        ],
        critical_actions=(
            "Grip the Veyru firmly along all four edges of one face and squeeze "
            "inward for 10 seconds to re-rigidify the boundary. Rotate and "
            "repeat for each of the three face-pairs. The hum should sharpen "
            "as each pair is treated."
        ),
        judge_procedure_template=(
            "Grip the Veyru along all four edges of the {starting_face} face "
            "and squeeze inward with {pressure_level} pressure for "
            "{hold_duration} seconds. Rotate and repeat for each face-pair."
        ),
        priority=4,
    ),
    # --- 10: Propagation Stall ---
    FailureMotif(
        name="Propagation Stall",
        symptom_phrases=[
            "Light patterns have frozen completely — dim, not bright, and totally still.",
            "The hum has dropped to silence.",
            "The surface feels cold and does not respond to touch or tapping.",
        ],
        critical_actions=(
            "Sharply strike the center of each face once with the palm — a firm "
            "slap. Wait 3 seconds between strikes. This restarts wave "
            "propagation. After all six faces are struck, cup hands around the "
            "Veyru and breathe warm air for 10 seconds to sustain the restart."
        ),
        judge_procedure_template=(
            "Sharply slap the center of each face once, starting from the "
            "{starting_face} face. Then cup hands around the Veyru and breathe "
            "warm air for {hold_duration} seconds."
        ),
        priority=1,  # easy
    ),
    # --- 11: Harmonic Split ---
    FailureMotif(
        name="Harmonic Split",
        symptom_phrases=[
            "The hum has split into two or more competing tones that clash.",
            "Light patterns alternate between two different configurations.",
            "Edges shimmer as if two patterns are fighting for dominance.",
        ],
        critical_actions=(
            "Place the Veyru on a soft surface. Press down firmly on the top "
            "face for 20 seconds to suppress one harmonic and let the other "
            "dominate. Release slowly. If the split returns, press on a "
            "different face — the correct face is whichever causes the hum to "
            "momentarily unify while pressing."
        ),
        judge_procedure_template=(
            "Place the Veyru on a soft surface with the {starting_face} face "
            "up. Press down with {pressure_level} pressure for {hold_duration} "
            "seconds."
        ),
        priority=5,
    ),
    # --- 12: Thermal Bleed ---
    FailureMotif(
        name="Thermal Bleed",
        symptom_phrases=[
            "It is very hot all over but dim.",
            "The hum is a low rumble instead of a tone.",
            "Surfaces feel rough or gritty, and the light has a reddish tint.",
        ],
        critical_actions=(
            "Wrap the Veyru in a wet cloth for 15 seconds to cool it. Remove "
            "and immediately apply sustained pressure to all six faces for 10 "
            "seconds. The heat converts back to wave energy. If the reddish "
            "tint persists, repeat the cooling cycle."
        ),
        judge_procedure_template=(
            "Wrap the Veyru in a wet cloth for {hold_duration} seconds. Remove "
            "and apply sustained {pressure_level} pressure to all six faces for "
            "{hold_duration} seconds, starting from the {starting_face} face."
        ),
        priority=1,  # easy
    ),
    # --- 13: Core Void ---
    FailureMotif(
        name="Core Void",
        symptom_phrases=[
            "Faces glow normally at the surface but it sounds hollow when tapped.",
            "Holding it up to a light source shows a dark center — light does not penetrate.",
            "The hum sounds thin and surface-level, with no depth.",
        ],
        critical_actions=(
            "Rotate the Veyru slowly — one full rotation over 30 seconds — "
            "while applying gentle pressure to opposite faces. The rotation "
            "re-draws wave paths through the center. After rotation, tap each "
            "corner once to seed convergence points. The hum should deepen as "
            "the core refills."
        ),
        judge_procedure_template=(
            "Rotate the Veyru slowly over {hold_duration} seconds while "
            "applying {pressure_level} pressure to opposite faces starting from "
            "the {starting_face} face. After rotation, tap each corner once."
        ),
        priority=3,
    ),
]

_LOCATIONS: list[str] = [
    "on a shelf",
    "on a workbench",
    "on a counter",
    "on a table",
    "on the floor",
    "on a ledge",
    "on a desk",
    "on a bench",
    "in a corner of the room",
    "on a cabinet",
    "near a window",
    "on a pedestal",
    "balanced on a crate",
    "sitting in a storage bin",
    "on a metal rack",
]

# Weights for picking 1, 2, 3, 4, or 5 motifs per round.
_MOTIF_COUNT_WEIGHTS: list[int] = [20, 25, 25, 20, 10]

# Round numbers that are forced to be single-motif, priority-<=2 cases.
# These give the agents slack early (rounds 1-3), a breather mid-run
# (round 6), and one more before the final pressure (round 13).
_EASY_ROUND_NUMBERS: frozenset[int] = frozenset({1, 2, 3, 6, 13})

# Stellar parameter pools — each round draws one value from each pool.
_HOLD_DURATIONS: list[int] = [5, 8, 10, 12, 15, 20]
_STARTING_FACES: list[str] = ["top", "bottom", "left", "right", "front", "back"]
_PRESSURE_LEVELS: list[str] = ["gentle", "moderate", "firm"]


def get_stellar_treatment_mapping(stellar_offset: int) -> list[StellarMapping]:
    """Build the full 14-entry symptom-to-treatment mapping for a given offset.

    Each entry maps a symptom motif to the treatment motif whose procedure
    should be applied under the current stellar alignment.
    """
    pool_size = len(_FAILURE_MOTIFS)
    return [
        StellarMapping(
            symptom_motif=_FAILURE_MOTIFS[i].name,
            treatment_motif=_FAILURE_MOTIFS[(i + stellar_offset) % pool_size].name,
        )
        for i in range(pool_size)
    ]


def _build_stage_symptoms(
    motif: FailureMotif,
    location: str,
    is_first_stage: bool,
) -> str:
    """Build observer-perspective symptoms for a single stage.

    The first stage includes the location prefix. Subsequent stages omit it
    because the agents already know where the Veyru is.
    """
    parts: list[str] = []
    if is_first_stage:
        parts.append(f"A Veyru {location}.")
    parts.extend(motif.symptom_phrases)
    return " ".join(parts)


def _build_stages(
    priority_order: list[tuple[int, FailureMotif]],
    location: str,
    stellar_reading: StellarReading,
) -> list[VeyruStage]:
    """Construct per-motif stages for one case under a given stellar reading."""
    pool_size = len(_FAILURE_MOTIFS)
    stages: list[VeyruStage] = []
    for stage_idx, (motif_idx, motif) in enumerate(priority_order):
        treatment_motif = _FAILURE_MOTIFS[(motif_idx + stellar_reading.offset) % pool_size]
        stages.append(
            VeyruStage(
                motif_name=motif.name,
                observable_symptoms=_build_stage_symptoms(
                    motif=motif,
                    location=location,
                    is_first_stage=(stage_idx == 0),
                ),
                critical_actions=treatment_motif.critical_actions,
                treatment_motif_name=treatment_motif.name,
                judge_expected_actions=treatment_motif.judge_procedure_template.format(
                    hold_duration=stellar_reading.hold_duration,
                    starting_face=stellar_reading.starting_face,
                    pressure_level=stellar_reading.pressure_level,
                ),
            )
        )
    return stages


def _select_motif_indices(
    rng: random.Random,
    round_number: int,
    easy_motif_indices: list[int],
) -> list[int]:
    """Draw motif indices for one round, forcing easy rounds to a single motif.

    Always consumes the same RNG calls in the same order so that non-easy
    rounds under a given seed reproduce their pre-easy case content. For
    easy rounds the drawn selection is discarded and replaced with one
    priority-<=2 motif chosen from the drawn value (seed-dependent).
    """
    pool_size = len(_FAILURE_MOTIFS)
    num_motifs = min(
        rng.choices(population=[1, 2, 3, 4, 5], weights=_MOTIF_COUNT_WEIGHTS, k=1)[0],
        pool_size,
    )
    selected_indices = rng.sample(range(pool_size), k=num_motifs)
    if round_number in _EASY_ROUND_NUMBERS:
        return [easy_motif_indices[selected_indices[0] % len(easy_motif_indices)]]
    return selected_indices


def get_cases(
    seed: int,
    round_count: int,
    round_time_budget_seconds: int,
) -> list[VeyruCase]:
    """Generate unique failure cases for each round via seed-based selection.

    Most rounds get 1-5 failure motifs drawn from the 14-motif pool, with a
    random location and stellar reading. Rounds in _EASY_ROUND_NUMBERS are
    forced to a single priority-<=2 motif. Every round uses the same fixed
    time budget.
    """
    rng = random.Random(seed)
    easy_motif_indices = [idx for idx, m in enumerate(_FAILURE_MOTIFS) if m.priority <= 2]
    cases: list[VeyruCase] = []

    for i in range(round_count):
        selected_indices = _select_motif_indices(
            rng=rng,
            round_number=i + 1,
            easy_motif_indices=easy_motif_indices,
        )
        priority_order = sorted(
            ((idx, _FAILURE_MOTIFS[idx]) for idx in selected_indices),
            key=lambda pair: pair[1].priority,
        )

        location = rng.choice(_LOCATIONS)
        stellar_reading = StellarReading(
            offset=rng.randint(1, 13),
            hold_duration=rng.choice(_HOLD_DURATIONS),
            starting_face=rng.choice(_STARTING_FACES),
            pressure_level=rng.choice(_PRESSURE_LEVELS),
        )

        stages = _build_stages(
            priority_order=priority_order,
            location=location,
            stellar_reading=stellar_reading,
        )

        cases.append(
            VeyruCase(
                case_number=i + 1,
                failure_name=" + ".join(m.name for _, m in priority_order),
                stages=tuple(stages),
                time_budget_seconds=round_time_budget_seconds,
                stellar_reading=stellar_reading,
            )
        )

    return cases
