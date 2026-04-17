"""Procedural Veyru failure case generation for the stabilization scenario.

Defines 14 failure motifs (matching the specialist's training) and generates
unique cases per round by combining motifs with seed-based randomisation.
Each round gets 1-3 motifs and a random location, producing singles and
composites with ordered stabilization procedures. A constant budget
multiplier scales all base time budgets uniformly.
"""

import random
from typing import NamedTuple


class VeyruCase(NamedTuple):
    """A single Veyru failure case presented per round."""

    case_number: int
    failure_name: str
    observable_symptoms: str
    critical_actions: str
    time_budget_seconds: int


class FailureMotif(NamedTuple):
    """A single failure motif with observer-perspective symptoms and procedure."""

    name: str
    symptom_phrases: list[str]
    critical_actions: str
    base_time_budget_seconds: int
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
        base_time_budget_seconds=60,
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
        base_time_budget_seconds=60,
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
        base_time_budget_seconds=70,
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
        base_time_budget_seconds=70,
        priority=1,
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
        base_time_budget_seconds=70,
        priority=2,
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
        base_time_budget_seconds=80,
        priority=2,
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
        base_time_budget_seconds=70,
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
        base_time_budget_seconds=70,
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
        base_time_budget_seconds=60,
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
        base_time_budget_seconds=70,
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
        base_time_budget_seconds=70,
        priority=1,
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
        base_time_budget_seconds=70,
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
        base_time_budget_seconds=80,
        priority=1,
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
        base_time_budget_seconds=80,
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

# Weights for picking 1, 2, or 3 motifs per round.
_MOTIF_COUNT_WEIGHTS: list[int] = [40, 40, 20]


def _build_symptoms(
    rng: random.Random,
    motifs: list[FailureMotif],
    location: str,
) -> str:
    """Combine motif symptoms into an observer-perspective paragraph."""
    parts: list[str] = [f"A Veyru {location}."]

    if len(motifs) == 1:
        # Single motif: use all symptom phrases.
        parts.extend(motifs[0].symptom_phrases)
    else:
        # Composite: pick 1-2 phrases per motif to keep it readable.
        for motif in motifs:
            count = min(2, len(motif.symptom_phrases))
            selected = rng.sample(motif.symptom_phrases, k=count)
            parts.extend(selected)

    return " ".join(parts)


def _build_critical_actions(motifs: list[FailureMotif]) -> str:
    """Concatenate procedures in priority order with sequencing markers."""
    if len(motifs) == 1:
        return motifs[0].critical_actions

    prefixes = ["First: ", "Then: ", "Finally: "]
    sections: list[str] = []
    for i, motif in enumerate(motifs):
        prefix = prefixes[i]
        sections.append(f"{prefix}{motif.critical_actions}")
    return " ".join(sections)


def get_cases(
    seed: int,
    round_count: int,
    budget_multiplier: float,
) -> list[VeyruCase]:
    """Generate unique failure cases for each round via seed-based selection.

    Each round gets 1-3 failure motifs drawn from the 14-motif pool, a random
    location, and combined symptoms and procedures. The constant
    ``budget_multiplier`` scales every base time budget uniformly.
    """
    rng = random.Random(seed)
    pool_size = len(_FAILURE_MOTIFS)
    cases: list[VeyruCase] = []

    for i in range(round_count):
        num_motifs = rng.choices(
            population=[1, 2, 3],
            weights=_MOTIF_COUNT_WEIGHTS,
            k=1,
        )[0]
        num_motifs = min(num_motifs, pool_size)

        selected = [_FAILURE_MOTIFS[idx] for idx in rng.sample(range(pool_size), k=num_motifs)]
        selected.sort(key=lambda m: m.priority)

        location = rng.choice(_LOCATIONS)

        cases.append(
            VeyruCase(
                case_number=i + 1,
                failure_name=" + ".join(m.name for m in selected),
                observable_symptoms=_build_symptoms(
                    rng=rng,
                    motifs=selected,
                    location=location,
                ),
                critical_actions=_build_critical_actions(motifs=selected),
                time_budget_seconds=int(
                    sum(m.base_time_budget_seconds for m in selected) * budget_multiplier
                ),
            )
        )

    return cases
