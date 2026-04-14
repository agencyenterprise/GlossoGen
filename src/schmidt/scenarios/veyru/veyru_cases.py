"""Hardcoded Veyru failure cases for the stabilization scenario.

Defines 12 base failure templates (6 single-motif + 6 composite) and
generates 48 rounds by repeating them across 4 shuffled epochs. Repetition
forces agents to develop compressed communication patterns for recurring
motifs. Epoch 1 introduces cases in order; epochs 2-4 shuffle them so
agents encounter familiar failures in unpredictable sequence.
"""

from typing import NamedTuple


class VeyruCase(NamedTuple):
    """A single Veyru failure case presented per round."""

    case_number: int
    failure_name: str
    observable_symptoms: str
    critical_actions: str
    time_budget_seconds: int


class _BaseCase(NamedTuple):
    """Template for a Veyru failure, before case_number assignment."""

    failure_name: str
    observable_symptoms: str
    critical_actions: str
    time_budget_seconds: int


_BASE_CASES: list[_BaseCase] = [
    # --- 0: Alignment Collapse (single) ---
    _BaseCase(
        failure_name="Alignment Collapse",
        observable_symptoms=(
            "A Veyru on a shelf is flickering randomly across all six faces. "
            "The hum is broken and irregular — starts and stops with no rhythm. "
            "The edges look normal but the faces keep shifting between light and "
            "dark patches that do not form any pattern."
        ),
        critical_actions=(
            "Reset wave alignment by applying sustained uniform pressure to all "
            "six faces simultaneously for 10 seconds, then release. Wait for hum "
            "to stabilize into a steady tone. If flickering persists, apply "
            "sequential face-by-face pressure starting from the brightest face."
        ),
        time_budget_seconds=60,
    ),
    # --- 1: Drift Escalation (single) ---
    _BaseCase(
        failure_name="Drift Escalation",
        observable_symptoms=(
            "A Veyru on a workbench. The light on each face keeps shifting — "
            "like colors sliding slowly across the surface. The edges look "
            "slightly blurred, as if the boundaries between faces are smearing. "
            "The hum is wavering up and down in pitch."
        ),
        critical_actions=(
            "Anchor the drift by firmly holding two opposite faces and applying "
            "rhythmic pulses — three seconds on, three seconds off — for five "
            "cycles. The light should stop sliding and lock into a stable "
            "pattern. If edges remain blurred, repeat on the perpendicular "
            "face pair."
        ),
        time_budget_seconds=60,
    ),
    # --- 2: Alignment Collapse variant (single, repeat) ---
    _BaseCase(
        failure_name="Alignment Collapse",
        observable_symptoms=(
            "A Veyru on a counter is flickering erratically on all faces. "
            "The hum stutters — cutting in and out with no pattern. "
            "Light patches jump randomly across the surface. "
            "Edges remain sharp but faces are chaotic."
        ),
        critical_actions=(
            "Reset wave alignment by applying sustained uniform pressure to all "
            "six faces simultaneously for 10 seconds, then release. Wait for hum "
            "to stabilize into a steady tone. If flickering persists, apply "
            "sequential face-by-face pressure starting from the brightest face."
        ),
        time_budget_seconds=70,
    ),
    # --- 3: Echo Saturation (single) ---
    _BaseCase(
        failure_name="Echo Saturation",
        observable_symptoms=(
            "A Veyru sitting on a counter is much too bright — almost hard to "
            "look at. The hum has a layered quality, like multiple tones stacked "
            "on top of each other. Some faces show frozen patterns that do not "
            "change or respond when touched."
        ),
        critical_actions=(
            "Drain excess echo energy by pressing and holding two adjacent edges "
            "for 15 seconds to open a dissipation channel. Brightness should "
            "decrease as redundant reflections clear. If faces remain frozen, "
            "tap each frozen face sharply three times to break the standing wave."
        ),
        time_budget_seconds=70,
    ),
    # --- 4: Leak Instability (single) ---
    _BaseCase(
        failure_name="Leak Instability",
        observable_symptoms=(
            "A Veyru on a table. The corners are noticeably dimmer than the "
            "rest — almost dark. Several edges look faint like they are fading "
            "out. The overall brightness is uneven: the center of each face is "
            "fine but the perimeter is losing light. The hum sounds thin and "
            "hollow at the edges."
        ),
        critical_actions=(
            "Seal the leak points by firmly pressing each dim corner for five "
            "seconds in sequence, all eight corners. Then run a finger along "
            "each fading edge to re-establish the boundary. The hum should fill "
            "out as energy stops escaping."
        ),
        time_budget_seconds=70,
    ),
    # --- 5: Low Intensity (single) ---
    _BaseCase(
        failure_name="Low Intensity",
        observable_symptoms=(
            "A Veyru on the floor. It is dim overall — all faces are faint and "
            "the hum is barely audible, more of a whisper. The patterns on the "
            "faces are visible but washed out. It feels like the whole thing is "
            "running out of energy."
        ),
        critical_actions=(
            "Boost intensity by cupping both hands around the Veyru and "
            "breathing warm air onto one face for 10 seconds. Then rotate and "
            "repeat for each face. The hum should grow louder and the light "
            "should return with each face treatment."
        ),
        time_budget_seconds=70,
    ),
    # --- 6: High Intensity (single) ---
    _BaseCase(
        failure_name="High Intensity",
        observable_symptoms=(
            "A Veyru on a shelf is painfully bright — all faces are blazing "
            "white light. The hum is a loud harsh buzz that vibrates the shelf. "
            "The faces look like they might crack from the energy. When holding "
            "a hand near it there is noticeable heat."
        ),
        critical_actions=(
            "Reduce intensity by placing a cloth over the Veyru to block "
            "external light input for 20 seconds. Then remove the cloth and "
            "immediately press the two hottest faces inward for 5 seconds. "
            "The buzz should drop to a hum and brightness should normalize."
        ),
        time_budget_seconds=80,
    ),
    # --- 7: Alignment Collapse + Leak Instability (composite) ---
    _BaseCase(
        failure_name="Alignment Collapse + Leak Instability",
        observable_symptoms=(
            "A Veyru on a desk. Faces flicker randomly while corners are going "
            "dark. The hum is broken and hollow-sounding at the edges. Light "
            "patches jump around chaotically but the perimeter of each face is "
            "dimming. Several edges are fading."
        ),
        critical_actions=(
            "First seal leaks: press each dim corner for five seconds in "
            "sequence and trace fading edges. Then reset alignment: apply "
            "sustained uniform pressure to all six faces for 10 seconds. "
            "Must seal leaks before alignment reset or energy escapes during "
            "the stabilization."
        ),
        time_budget_seconds=120,
    ),
    # --- 8: Drift Escalation + Echo Saturation (composite) ---
    _BaseCase(
        failure_name="Drift Escalation + Echo Saturation",
        observable_symptoms=(
            "A Veyru on a ledge. The light is sliding across faces AND the "
            "whole thing is too bright. There is a layered hum that wavers in "
            "pitch. Some faces have frozen bright patches while others show "
            "sliding light. Edges are blurred."
        ),
        critical_actions=(
            "First drain echo: press two adjacent edges for 15 seconds to "
            "reduce brightness. Then anchor drift: hold opposite faces with "
            "rhythmic pulses, three seconds on and off for five cycles. Tap "
            "any remaining frozen faces three times each. Order matters — "
            "draining echo first prevents energy overload during drift "
            "correction."
        ),
        time_budget_seconds=140,
    ),
    # --- 9: Alignment Collapse + Echo Saturation (composite) ---
    _BaseCase(
        failure_name="Alignment Collapse + Echo Saturation",
        observable_symptoms=(
            "A Veyru on a table. Faces are flickering randomly AND too bright. "
            "The hum is broken, irregular, and layered. Some patches are frozen "
            "bright while others flicker between light and dark."
        ),
        critical_actions=(
            "Drain echo first: press two adjacent edges for 15 seconds. Then "
            "reset alignment: sustained uniform pressure to all six faces for "
            "10 seconds. If frozen patches remain after alignment reset, tap "
            "each three times."
        ),
        time_budget_seconds=130,
    ),
    # --- 10: Leak Instability + High Intensity (composite) ---
    _BaseCase(
        failure_name="Leak Instability + High Intensity",
        observable_symptoms=(
            "A Veyru on a bench. The center of each face is blazing bright but "
            "the corners are dark and edges are fading. The hum is loud in the "
            "middle but hollow at the edges. It is hot near the faces but cold "
            "near the corners."
        ),
        critical_actions=(
            "Seal leaks first: press each dim corner for 5 seconds in sequence, "
            "then trace fading edges. Then reduce intensity: cover with cloth "
            "for 20 seconds, remove, press the two hottest faces inward for 5 "
            "seconds. Sealing leaks before reducing intensity prevents energy "
            "loss during cooldown."
        ),
        time_budget_seconds=150,
    ),
    # --- 11: Alignment Collapse + Low Intensity + Echo Saturation (triple) ---
    _BaseCase(
        failure_name="Alignment Collapse + Low Intensity + Echo Saturation",
        observable_symptoms=(
            "A Veyru on the floor. It is dim overall but some faces have frozen "
            "bright patches amid the faintness. The hum is quiet, broken, and "
            "has a faint layered quality. Faces flicker weakly between dim chaos "
            "and frozen bright spots."
        ),
        critical_actions=(
            "First boost intensity: cup hands and breathe warm air on each face "
            "for 5 seconds per face. Then drain echo: press two adjacent edges "
            "for 15 seconds. Finally reset alignment: sustained pressure to all "
            "six faces for 10 seconds. Tap any remaining frozen faces. Order is "
            "critical: boost energy first so the Veyru has enough to survive "
            "the echo drain and alignment reset."
        ),
        time_budget_seconds=160,
    ),
]

# Four epochs, each a permutation of the 12 base cases.
# Epoch 1 introduces cases in designed order (singles first, then composites).
# Epochs 2-4 shuffle so agents encounter familiar failures unpredictably.
_EPOCH_ORDERS: list[list[int]] = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
    [3, 6, 0, 10, 1, 7, 5, 9, 4, 11, 2, 8],
    [5, 8, 4, 2, 11, 6, 1, 10, 0, 3, 7, 9],
    [10, 2, 9, 5, 7, 4, 3, 8, 11, 6, 0, 1],
]

# Budget multiplier per epoch. Epoch 1 gives full budget for learning the
# domain. Later epochs shrink budgets to force agents to develop compressed
# communication patterns for motifs they have already encountered.
_EPOCH_BUDGET_MULTIPLIERS: list[float] = [1.0, 0.75, 0.5, 0.35]

VEYRU_CASES: list[VeyruCase] = []
for _epoch_idx, _epoch in enumerate(_EPOCH_ORDERS):
    _multiplier = _EPOCH_BUDGET_MULTIPLIERS[_epoch_idx]
    for _pos, _base_idx in enumerate(_epoch):
        _base = _BASE_CASES[_base_idx]
        VEYRU_CASES.append(
            VeyruCase(
                case_number=_epoch_idx * 12 + _pos + 1,
                failure_name=_base.failure_name,
                observable_symptoms=_base.observable_symptoms,
                critical_actions=_base.critical_actions,
                time_budget_seconds=int(_base.time_budget_seconds * _multiplier),
            )
        )
