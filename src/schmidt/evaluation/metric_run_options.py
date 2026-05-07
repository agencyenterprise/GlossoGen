"""Per-invocation options forwarded from the ``schmidt evaluate`` CLI to metric factories.

Lives in its own module so ``scenario_protocol.py`` can import the type without
forming a circular dependency with ``metric_protocol.py``.
"""

from pydantic import BaseModel


class MetricRunOptions(BaseModel):
    """Options threaded through ``scenario.run_evaluation`` into each metric factory.

    Carries flags only some metrics consume — most factories ignore the
    value and instantiate their metric with no constructor arguments.
    Every field is optional; the factory of any metric that requires a
    given option raises when the user has not supplied it. The
    ``protocol_probe`` metric reads ``probe_round`` and ``probe_replicas``.
    """

    probe_round: int | None
    probe_replicas: int | None
