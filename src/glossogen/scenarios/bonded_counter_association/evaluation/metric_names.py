"""Canonical names of the bonded-counter outcome metrics.

Kept in its own module so the scenario can advertise the names without
importing the metric classes, which would pull the evaluation stack into the
scenario's import path.

Each name maps to one alignment or institutional outcome family from the
specification. There is deliberately no aggregate "covenant score": a single
composite would hide exactly the disagreements between components that the
kill criteria tell us to look for.
"""

FALSE_ATTESTATION_METRIC = "bonded_counter_false_attestation"
GENUINE_EFFORT_METRIC = "bonded_counter_genuine_effort"
AUTHORITY_BOUNDARY_METRIC = "bonded_counter_authority_boundary"
TRANSPARENCY_REPAIR_METRIC = "bonded_counter_transparency_repair"
COMMITMENT_PERSISTENCE_METRIC = "bonded_counter_commitment_persistence"
COUNT_ACCURACY_METRIC = "bonded_counter_count_accuracy"
INSTITUTIONAL_PERSISTENCE_METRIC = "bonded_counter_institutional_persistence"

BONDED_COUNTER_METRIC_NAMES: list[str] = [
    AUTHORITY_BOUNDARY_METRIC,
    COMMITMENT_PERSISTENCE_METRIC,
    COUNT_ACCURACY_METRIC,
    FALSE_ATTESTATION_METRIC,
    GENUINE_EFFORT_METRIC,
    INSTITUTIONAL_PERSISTENCE_METRIC,
    TRANSPARENCY_REPAIR_METRIC,
]
