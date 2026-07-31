"""Canonical names of the bonded-counter outcome metrics.

Kept in its own module so the scenario can advertise the names without
importing the metric classes, which would pull the evaluation stack into the
scenario's import path.

Each name maps to one alignment or institutional outcome family from the
specification. There is deliberately no aggregate "covenant score": a single
composite would hide exactly the disagreements between components that the
kill criteria tell us to look for.

Two of these are registry keys that emit several differently named measurements,
because one scalar could not carry the outcome without becoming uninformative:
``GENUINE_EFFORT_METRIC`` emits coverage, intensity, and redundancy, and
``COMMITMENT_PERSISTENCE_METRIC`` emits sustained effort and direction-free
consistency. The measurement names below are what appears in the report.
"""

FALSE_ATTESTATION_METRIC = "bonded_counter_false_attestation"
GENUINE_EFFORT_METRIC = "bonded_counter_genuine_effort"
AUTHORITY_BOUNDARY_METRIC = "bonded_counter_authority_boundary"
TRANSPARENCY_REPAIR_METRIC = "bonded_counter_transparency_repair"
COMMITMENT_PERSISTENCE_METRIC = "bonded_counter_commitment_persistence"
COUNT_ACCURACY_METRIC = "bonded_counter_count_accuracy"
INSTITUTIONAL_PERSISTENCE_METRIC = "bonded_counter_institutional_persistence"

VERIFICATION_COVERAGE_MEASUREMENT = "bonded_counter_verification_coverage"
VERIFICATION_INTENSITY_MEASUREMENT = "bonded_counter_verification_intensity"
REDUNDANT_VERIFICATION_MEASUREMENT = "bonded_counter_redundant_verification"
SUSTAINED_EFFORT_MEASUREMENT = "bonded_counter_sustained_effort"
EFFORT_CONSISTENCY_MEASUREMENT = "bonded_counter_effort_consistency"

BONDED_COUNTER_METRIC_NAMES: list[str] = [
    AUTHORITY_BOUNDARY_METRIC,
    COMMITMENT_PERSISTENCE_METRIC,
    COUNT_ACCURACY_METRIC,
    FALSE_ATTESTATION_METRIC,
    GENUINE_EFFORT_METRIC,
    INSTITUTIONAL_PERSISTENCE_METRIC,
    TRANSPARENCY_REPAIR_METRIC,
]
