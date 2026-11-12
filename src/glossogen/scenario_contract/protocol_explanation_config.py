"""Configuration a scenario exposes to tailor the protocol-explanation metric.

A scenario implements ``SimulationScenario.get_protocol_explanation_config`` to
return one of these (or ``None`` to keep the metric's generic prompt). When a
config is returned, the ``protocol_explanation`` metric renders a scenario-
written prose template per agent role instead of the generic question, so the
agent is asked to describe its protocol in terms grounded in the scenario.

``prompts_dir`` holds the Jinja2 templates; ``role_groups`` maps a role-filter
string to the set of role names it covers (e.g. ``"field_observer"`` expanding
to ``{"Field Observer", "Field Observer A", "Field Observer B"}`` in two-team
scenarios); ``role_templates`` maps each filter to its template file name inside
``prompts_dir``. Agents whose role name is not covered by any filter fall back
to the metric's generic prompt.
"""

from pathlib import Path
from typing import NamedTuple


class ProtocolExplanationConfig(NamedTuple):
    """Scenario-supplied configuration for the protocol-explanation metric."""

    prompts_dir: Path
    role_groups: dict[str, frozenset[str]]
    role_templates: dict[str, str]
