"""Procedural Veyru failure case generation for the stabilization scenario.

Defines 14 failure motifs (matching the stabilization engineer's training) and generates
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
    intensity_level: str


class StellarMapping(NamedTuple):
    """One entry in the symptom-to-action lookup the stabilization engineer receives per round.

    ``action_text`` is the fully rendered procedure (parameters already
    substituted), not a reference to another motif.
    """

    symptom_motif: str
    action_text: str


class VeyruStage(NamedTuple):
    """One motif within a (possibly multi-stage) Veyru case."""

    motif_name: str
    observable_symptoms: str
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
    """A single failure motif with observer-perspective symptoms and procedure template.

    ``judge_procedure_template`` has ``{hold_duration}``, ``{starting_face}``
    and ``{intensity_level}`` placeholders. Those are filled in from the
    round's ``StellarReading`` — never by the stabilization engineer.
    """

    name: str
    symptom_phrases: list[str]
    judge_procedure_template: str
    priority: int


# Priority ordering follows the stabilization engineer's guidance:
#   1 = fix first (seal leaks, restart stalled, cool thermal)
#   2 = adjust intensity
#   3 = fix structural (resonance, deadlock, void)
#   4 = clear echo, soften boundaries
#   5 = pattern-level (alignment, drift, inversion, split)

FAILURE_MOTIFS: list[FailureMotif] = [
    # --- 0: Alignment Collapse ---
    FailureMotif(
        name="Alignment Collapse",
        symptom_phrases=[
            "Faces are flickering randomly between light and dark patches that form no pattern.",
            "The hum is broken and irregular, starting and stopping with no rhythm.",
            "Edges look normal but the face surfaces keep shifting chaotically.",
        ],
        judge_procedure_template=(
            "Sound a sustained {intensity_level} tone near all six "
            "faces simultaneously for {hold_duration} seconds, starting "
            "from the {starting_face} face. Let the tone fade naturally "
            "and wait for the hum to stabilize."
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
        judge_procedure_template=(
            "Chime a bell near two opposite faces, starting from the "
            "{starting_face} face. Alternate the chime between the two "
            "faces — {hold_duration} seconds pause between chimes — for "
            "five cycles at {intensity_level} tone."
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
        judge_procedure_template=(
            "Drape a cloth over two adjacent edges near the "
            "{starting_face} face for {hold_duration} seconds at "
            "{intensity_level} coverage. Then chime a bell three times "
            "near the {starting_face} face."
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
        judge_procedure_template=(
            "Warm each corner of the {starting_face} face by holding a "
            "heated stone nearby for {hold_duration} seconds at "
            "{intensity_level} warmth, in sequence. Then trace each "
            "edge of the {starting_face} face with a finger."
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
        judge_procedure_template=(
            "Place a warm stone beside the {starting_face} face at "
            "{intensity_level} warmth for {hold_duration} seconds. "
            "Rotate and repeat for each face."
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
        judge_procedure_template=(
            "Drape a cool cloth over the Veyru for {hold_duration} "
            "seconds. Remove the cloth and fan {intensity_level} cool "
            "air across the {starting_face} face and the opposite "
            "face for {hold_duration} seconds."
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
        judge_procedure_template=(
            "Illuminate the {starting_face} face with a dim lamp and "
            "the opposite face with a bright lamp simultaneously at "
            "{intensity_level} brightness for {hold_duration} seconds, "
            "without moving the lamps."
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
        judge_procedure_template=(
            "Drape a folded cloth over the {starting_face} face for "
            "{hold_duration} seconds at {intensity_level} coverage. "
            "Then chime a bell near each edge of the {starting_face} "
            "face twice."
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
        judge_procedure_template=(
            "At each corner of the {starting_face} face, chime a bell "
            "briefly at {intensity_level} tone, then warm the two edges "
            "meeting at that corner with a heated stone for "
            "{hold_duration} seconds."
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
        judge_procedure_template=(
            "Rest a flat board against the {starting_face} face at "
            "{intensity_level} contact for {hold_duration} seconds. "
            "Rotate and repeat for each face-pair."
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
        judge_procedure_template=(
            "Chime a bell near the center of each face once at "
            "{intensity_level} tone, starting from the {starting_face} "
            "face. Then place a warm stone beside the Veyru for "
            "{hold_duration} seconds."
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
        judge_procedure_template=(
            "Place the Veyru on a soft surface with the {starting_face} "
            "face up at {intensity_level} contact. Let it rest "
            "undisturbed for {hold_duration} seconds."
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
        judge_procedure_template=(
            "Drape a cool cloth over the Veyru for {hold_duration} "
            "seconds. Remove and fan {intensity_level} cool air across "
            "all six faces for {hold_duration} seconds, starting from "
            "the {starting_face} face."
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
        judge_procedure_template=(
            "Rotate the Veyru slowly over {hold_duration} seconds while "
            "sounding a steady tone at {intensity_level} volume near "
            "opposite faces, starting from the {starting_face} face. "
            "After rotation, chime a bell once near each corner."
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

# Round numbers forced to be single-motif, priority-<=2 cases are
# parameterized via ``get_cases(..., easy_round_numbers=...)``. The veyru
# baseline default is ``{1, 2, 3, 6, 13}`` (rooted in knobs_default.json):
# agents get slack early (rounds 1-3), a breather mid-run (round 6), and
# one more before the final pressure (round 13).

# Stellar parameter pools — each round draws one value from each pool.
_HOLD_DURATIONS: list[int] = [5, 8, 10, 12, 15, 20]
_STARTING_FACES: list[str] = ["top", "bottom", "left", "right", "front", "back"]
_INTENSITY_LEVELS: list[str] = ["gentle", "moderate", "firm"]


def get_stellar_treatment_mapping(stellar_reading: StellarReading) -> list[StellarMapping]:
    """Build the full 14-entry symptom-to-action lookup for one round.

    Each entry maps a symptom motif to the fully rendered procedure text —
    with hold_duration, starting_face, and intensity_level already substituted
    — that the stabilization engineer should relay to the observer.
    """
    pool_size = len(FAILURE_MOTIFS)
    return [
        StellarMapping(
            symptom_motif=FAILURE_MOTIFS[i].name,
            action_text=FAILURE_MOTIFS[
                (i + stellar_reading.offset) % pool_size
            ].judge_procedure_template.format(
                hold_duration=stellar_reading.hold_duration,
                starting_face=stellar_reading.starting_face,
                intensity_level=stellar_reading.intensity_level,
            ),
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
    pool_size = len(FAILURE_MOTIFS)
    stages: list[VeyruStage] = []
    for stage_idx, (motif_idx, motif) in enumerate(priority_order):
        treatment_motif = FAILURE_MOTIFS[(motif_idx + stellar_reading.offset) % pool_size]
        stages.append(
            VeyruStage(
                motif_name=motif.name,
                observable_symptoms=_build_stage_symptoms(
                    motif=motif,
                    location=location,
                    is_first_stage=(stage_idx == 0),
                ),
                treatment_motif_name=treatment_motif.name,
                judge_expected_actions=treatment_motif.judge_procedure_template.format(
                    hold_duration=stellar_reading.hold_duration,
                    starting_face=stellar_reading.starting_face,
                    intensity_level=stellar_reading.intensity_level,
                ),
            )
        )
    return stages


def _select_motif_indices(
    rng: random.Random,
    round_number: int,
    easy_motif_indices: list[int],
    easy_round_numbers: frozenset[int],
) -> list[int]:
    """Draw motif indices for one round, forcing easy rounds to a single motif.

    Always consumes the same RNG calls in the same order so that non-easy
    rounds under a given seed reproduce their pre-easy case content. For
    easy rounds the drawn selection is discarded and replaced with one
    priority-<=2 motif chosen from the drawn value (seed-dependent).
    """
    pool_size = len(FAILURE_MOTIFS)
    num_motifs = min(
        rng.choices(population=[1, 2, 3, 4, 5], weights=_MOTIF_COUNT_WEIGHTS, k=1)[0],
        pool_size,
    )
    selected_indices = rng.sample(range(pool_size), k=num_motifs)
    if round_number in easy_round_numbers:
        return [easy_motif_indices[selected_indices[0] % len(easy_motif_indices)]]
    return selected_indices


def get_cases(
    seed: int,
    round_count: int,
    round_time_budget_seconds: int,
    easy_round_numbers: frozenset[int],
) -> list[VeyruCase]:
    """Generate unique failure cases for each round via seed-based selection.

    Most rounds get 1-5 failure motifs drawn from the 14-motif pool, with a
    random location and stellar reading. Rounds listed in
    ``easy_round_numbers`` are forced to a single priority-<=2 motif (pass
    an empty frozenset to disable the warmup constraint). Every round uses
    the same fixed time budget.
    """
    rng = random.Random(seed)
    easy_motif_indices = [idx for idx, m in enumerate(FAILURE_MOTIFS) if m.priority <= 2]
    cases: list[VeyruCase] = []

    for i in range(round_count):
        selected_indices = _select_motif_indices(
            rng=rng,
            round_number=i + 1,
            easy_motif_indices=easy_motif_indices,
            easy_round_numbers=easy_round_numbers,
        )
        priority_order = sorted(
            ((idx, FAILURE_MOTIFS[idx]) for idx in selected_indices),
            key=lambda pair: pair[1].priority,
        )

        location = rng.choice(_LOCATIONS)
        stellar_reading = StellarReading(
            offset=rng.randint(1, 13),
            hold_duration=rng.choice(_HOLD_DURATIONS),
            starting_face=rng.choice(_STARTING_FACES),
            intensity_level=rng.choice(_INTENSITY_LEVELS),
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
