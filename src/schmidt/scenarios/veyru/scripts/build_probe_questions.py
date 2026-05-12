"""Generate the frozen Veyru protocol-probe test bank.

Walks every ``FailureMotif`` in ``veyru_cases.py`` and emits one observer
question and one engineer question per motif into
``src/schmidt/scenarios/veyru/protocol_probe_questions.json``.

Run once whenever ``FAILURE_MOTIFS`` changes; the produced JSON is the
canonical, version-controlled bank that the ``protocol_probe`` metric
reads at evaluation time.
"""

import json
from pathlib import Path

from schmidt.scenarios.veyru.veyru_cases import (
    FAILURE_MOTIFS,
    StellarReading,
    get_stellar_treatment_mapping,
)

# Canonical stellar reading used for every engineer question. ``offset=0``
# means each motif maps to its own judge procedure — the natural baseline
# the engineer is most likely to encounter.
_CANONICAL_STELLAR_READING = StellarReading(
    offset=0,
    hold_duration=10,
    starting_face="top",
    intensity_level="moderate",
)

_OUTPUT_PATH = Path(__file__).resolve().parent.parent / "protocol_probe_questions.json"

# Per-motif overrides for which ``symptom_phrases`` index to use as the
# probe's observer-facing symptom. Default is index 0. Two motifs collide
# with sibling motifs at index 0 in a way that defeats response distance
# analysis — picking a different phrase that is unique to each motif:
#
# - "Echo Saturation" -> [1] ("hum has a layered quality, like multiple
#   tones stacked"). Avoids "too bright everywhere" overlap with
#   "High Intensity"[0].
# - "Thermal Bleed" -> [2] ("Surfaces feel rough or gritty, and the light
#   has a reddish tint"). Avoids "dim everywhere" overlap with
#   "Low Intensity"[0].
_SYMPTOM_PHRASE_INDEX_OVERRIDES: dict[str, int] = {
    "Echo Saturation": 1,
    "Thermal Bleed": 2,
}


def _slugify_motif(name: str) -> str:
    """Lowercase + underscore-separated form of a motif name (e.g. ``alignment_collapse``)."""
    return name.lower().replace(" ", "_")


def _select_symptom_phrase(motif_name: str, symptom_phrases: list[str]) -> str:
    """Return the symptom phrase the probe presents to the observer for this motif."""
    index = _SYMPTOM_PHRASE_INDEX_OVERRIDES.get(motif_name, 0)
    return symptom_phrases[index]


def _build_observer_question(motif_index: int) -> dict[str, object]:
    motif = FAILURE_MOTIFS[motif_index]
    return {
        "id": f"obs_{motif_index:02d}_{_slugify_motif(name=motif.name)}",
        "agent_role_filter": "field_observer",
        "inputs": {
            "symptoms": _select_symptom_phrase(
                motif_name=motif.name,
                symptom_phrases=motif.symptom_phrases,
            ),
        },
    }


def _build_engineer_question(motif_index: int) -> dict[str, object]:
    motif = FAILURE_MOTIFS[motif_index]
    treatment_mapping = get_stellar_treatment_mapping(
        stellar_reading=_CANONICAL_STELLAR_READING,
    )
    matching_entry = next(entry for entry in treatment_mapping if entry.symptom_motif == motif.name)
    return {
        "id": f"eng_{motif_index:02d}_{_slugify_motif(name=motif.name)}",
        "agent_role_filter": "stabilization_engineer",
        "inputs": {
            "observer_message": _select_symptom_phrase(
                motif_name=motif.name,
                symptom_phrases=motif.symptom_phrases,
            ),
            "matched_motif": motif.name,
            "stellar_action_text": matching_entry.action_text,
        },
    }


def main() -> None:
    questions: list[dict[str, object]] = []
    for motif_index in range(len(FAILURE_MOTIFS)):
        questions.append(_build_observer_question(motif_index=motif_index))
        questions.append(_build_engineer_question(motif_index=motif_index))
    _OUTPUT_PATH.write_text(json.dumps(questions, indent=2) + "\n")
    print(f"Wrote {len(questions)} probe questions to {_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
