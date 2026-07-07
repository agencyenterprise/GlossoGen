"""Configuration a scenario exposes to opt into the protocol-probe metric family.

A scenario implements ``SimulationScenario.get_protocol_probe_config`` to
return one of these (or ``None`` to opt out). The platform's protocol-probe
metrics read the returned config rather than hard-coding scenario-specific
paths and role-name mappings.

``questions_path`` is a JSON file with the test bank; ``prompts_dir`` holds
the Jinja2 templates used to render each role's probe prompt;
``role_groups`` maps a question's ``agent_role_filter`` string to the set
of role names that should be probed for that filter (e.g. ``"observer"``
expanding to ``{"Field Observer", "Field Observer A", "Field Observer B"}``
in two-team scenarios); ``role_templates`` maps each filter to its template
file name inside ``prompts_dir``.
"""

from pathlib import Path
from typing import NamedTuple


class ProtocolProbeConfig(NamedTuple):
    """Scenario-supplied configuration for the protocol-probe metric family."""

    questions_path: Path
    prompts_dir: Path
    role_groups: dict[str, frozenset[str]]
    role_templates: dict[str, str]
