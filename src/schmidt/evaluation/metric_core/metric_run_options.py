"""Per-invocation options forwarded from the ``schmidt evaluate`` CLI to metric factories.

Lives in its own module so ``scenario_protocol.py`` can import the type without
forming a circular dependency with ``metric_protocol.py``.
"""

from pathlib import Path

from pydantic import BaseModel, Field


class MetricRunOptions(BaseModel):
    """Options threaded through ``scenario.run_evaluation`` into each metric factory.

    Carries flags only some metrics consume — most factories ignore the
    value and instantiate their metric with no constructor arguments.
    Every field is optional; the factory of any metric that requires a
    given option raises when the user has not supplied it. The
    ``protocol_probe`` metric reads ``probe_round`` and ``probe_replicas``;
    the ``communication_feature_presence`` metric reads ``ontology_path``.
    """

    probe_round: int | None = Field(
        description=(
            "Cutoff for the probe metric's reconstructed history. The filter "
            "drops every tool call whose ``round_number >= probe_round``, so "
            "the resulting history covers rounds ``1..probe_round-1`` "
            "(inclusive). To capture the agent's state at the END of round R, "
            "pass ``probe_round=R+1``. ``None`` keeps the full end-of-run "
            "history."
        ),
    )
    probe_replicas: int | None = Field(
        description=(
            "Number of independent probe-LLM calls to make per (agent, "
            "question) pair. Required when running the ``protocol_probe`` "
            "metric; ignored otherwise."
        ),
    )
    ontology_path: Path | None = Field(
        description=(
            "Path to a consolidated communication-feature ontology JSON file "
            "(typically ``<runs_dir>/<scenario_name>/_ontology/<version>.json``). "
            "Optional for the ``communication_feature_presence`` metric: when "
            "``None`` the metric auto-resolves the most recently modified "
            "ontology JSON under that per-scenario directory. Ignored by "
            "other metrics."
        ),
    )
