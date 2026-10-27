"""Configuration a scenario exposes to opt into the protocol-probe metric family.

A scenario implements ``SimulationScenario.get_protocol_probe_config`` to
return one of these (or ``None`` to opt out). The platform's protocol-probe
metrics read the returned config rather than hard-coding scenario-specific
paths and role-name mappings.

The test bank itself is read here too, so a caller that only needs to know
what the bank asks does not import the metric.

``questions_path`` is a JSON file with the test bank; ``prompts_dir`` holds
the Jinja2 templates used to render each role's probe prompt;
``role_groups`` maps a question's ``agent_role_filter`` string to the set
of role names that should be probed for that filter (e.g. ``"observer"``
expanding to ``{"Field Observer", "Field Observer A", "Field Observer B"}``
in two-team scenarios); ``role_templates`` maps each filter to its template
file name inside ``prompts_dir``.
"""

import json
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel


class ProtocolProbeConfig(NamedTuple):
    """Scenario-supplied configuration for the protocol-probe metric family."""

    questions_path: Path
    prompts_dir: Path
    role_groups: dict[str, frozenset[str]]
    role_templates: dict[str, str]


class ProbeQuestion(BaseModel):
    """One entry in the frozen test bank file.

    ``inputs`` is rendered into the role's template, so its keys are the
    variables that template reads. A value keeps the JSON type it was written
    as: a template comparing one with ``==`` reads a quoted number as a string
    and takes the wrong branch.
    """

    id: str
    agent_role_filter: str
    inputs: dict[str, str | int]


def load_probe_questions(path: Path) -> list[ProbeQuestion]:
    """Read the frozen test bank JSON and validate each entry."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [ProbeQuestion.model_validate(entry) for entry in raw]
