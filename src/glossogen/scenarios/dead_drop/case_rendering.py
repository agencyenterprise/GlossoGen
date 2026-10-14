"""The text of one agent's case, as its case file or its briefing holds it."""

from typing import NamedTuple

from glossogen.scenarios.dead_drop.case_generation import AgentCase
from glossogen.scenarios.dead_drop.ids import CASE_TEMPLATE
from glossogen.template_renderer import TemplateRenderer


class CodebookLine(NamedTuple):
    """One codebook entry as the case template reads it."""

    key: str
    value: str


def render_case(renderer: TemplateRenderer, round_number: int, agent_case: AgentCase) -> str:
    """``agent_case`` for round ``round_number``, rendered with the case template."""
    return renderer.render(
        template_name=CASE_TEMPLATE,
        template_variables={
            "round_number": round_number,
            "codebook": [
                CodebookLine(key=key, value=value) for key, value in agent_case.codebook.items()
            ],
            "requests": list(agent_case.requests),
        },
    )
