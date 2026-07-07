"""Shared prompts and constants for the agent communication protocol.

All agent runners use the same communication protocol: agents call
read_notifications(), read channels, send messages, and loop until done.
Prompt text lives in Jinja2 templates under ``runners/prompts/``.
"""

from pathlib import Path

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


def build_full_system_prompt(base_prompt: str, role_name: str) -> str:
    """Combine an agent's base system prompt with the communication protocol instructions."""
    suffix = _renderer.render(
        template_name="system_suffix.jinja",
        template_variables={"role_name": role_name},
    )
    return base_prompt + "\n\n" + suffix
