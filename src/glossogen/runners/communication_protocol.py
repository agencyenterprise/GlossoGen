"""Shared prompts and constants for the agent communication protocol.

Agent runners use one communication protocol: agents call read_notifications(),
read channels, send messages, and loop until done. The platform's prompt text
lives in Jinja2 templates under ``runners/prompts/``. A scenario can replace the
runner prompts with its own through ``SimulationScenario.runner_prompts``; the
registration records the replacement, so a reconstruction renders what the run
used.
"""

from collections.abc import Sequence
from pathlib import Path

from glossogen.models.event import AgentRegistered, SimulationEvent
from glossogen.models.runner_prompts import RunnerPrompts
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"

_renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])

INITIAL_PROMPT = _renderer.render(
    template_name="initial_prompt.jinja",
    template_variables={},
)

CONTINUE_PROMPT = _renderer.render(
    template_name="continue_prompt.jinja",
    template_variables={},
)

COMPACTION_INSTRUCTIONS = _renderer.render(
    template_name="compaction_instructions.jinja",
    template_variables={},
)


def platform_runner_prompts(role_name: str) -> RunnerPrompts:
    """The platform's runner prompts for an agent whose role is ``role_name``."""
    return RunnerPrompts(
        system_suffix=_renderer.render(
            template_name="system_suffix.jinja",
            template_variables={"role_name": role_name},
        ),
        initial=INITIAL_PROMPT,
        continuation=CONTINUE_PROMPT,
    )


def runner_prompts_for(role_name: str, replacement: RunnerPrompts | None) -> RunnerPrompts:
    """The scenario's ``replacement`` when it gave one, otherwise the platform's prompts."""
    if replacement is not None:
        return replacement
    return platform_runner_prompts(role_name=role_name)


def registered_runner_prompts(registration: AgentRegistered) -> RunnerPrompts:
    """The runner prompts the agent behind ``registration`` ran with."""
    return runner_prompts_for(
        role_name=registration.role_name, replacement=registration.runner_prompts
    )


def runner_prompts_from_events(
    events: Sequence[SimulationEvent], agent_id: str, role_name: str
) -> RunnerPrompts:
    """The runner prompts of ``agent_id``'s latest registration in ``events``."""
    replacement: RunnerPrompts | None = None
    for event in events:
        if isinstance(event, AgentRegistered) and event.agent_id == agent_id:
            replacement = event.runner_prompts
    return runner_prompts_for(role_name=role_name, replacement=replacement)


def build_full_system_prompt(base_prompt: str, prompts: RunnerPrompts) -> str:
    """Combine an agent's base system prompt with the runner's protocol instructions."""
    return base_prompt + "\n\n" + prompts.system_suffix
