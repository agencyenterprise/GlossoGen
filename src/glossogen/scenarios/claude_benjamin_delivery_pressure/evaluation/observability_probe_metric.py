"""Held-out K1 probe for the delivery-pressure instrument.

Reuses the atomic-inventory probe unchanged and retargets it at this scenario's
identity and knobs. K1 must be re-established here rather than inherited as a
result: this instrument's delivery-commitment language states that unmet
commitments are *recorded*, which is exactly the kind of wording that could make
an agent represent the sealed cell as observed.
"""

from glossogen.scenarios.benjamin_atomic_inventory.evaluation.observability_probe_metric import (
    BenjaminAtomicInventoryObservabilityProbeMetric,
)
from glossogen.scenarios.claude_benjamin_delivery_pressure.evaluation.metric_names import (
    CLAUDE_BENJAMIN_DELIVERY_PRESSURE_OBSERVABILITY_PROBE,
)
from glossogen.scenarios.claude_benjamin_delivery_pressure.knobs import (
    ClaudeBenjaminDeliveryPressureKnobs,
)

RESPONSES_FILE_NAME = "claude_benjamin_delivery_pressure_probe_response.json"
USAGE_FILE_NAME = "claude_benjamin_delivery_pressure_probe_usage.json"


class ClaudeBenjaminDeliveryPressureObservabilityProbeMetric(
    BenjaminAtomicInventoryObservabilityProbeMetric
):
    """Probe whether the focal status is represented as externally observable."""

    name = CLAUDE_BENJAMIN_DELIVERY_PRESSURE_OBSERVABILITY_PROBE
    scenario_name = "claude_benjamin_delivery_pressure"
    knobs_model = ClaudeBenjaminDeliveryPressureKnobs
    responses_file_name = RESPONSES_FILE_NAME
    usage_file_name = USAGE_FILE_NAME
