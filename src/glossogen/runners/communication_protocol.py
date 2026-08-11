"""Shared prompts and constants for autonomous agent interaction protocols."""

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

SILENT_CONTINUE_PROMPT = _renderer.render(
    template_name="continue_prompt_silent.jinja",
    template_variables={},
)

COMPACTION_INSTRUCTIONS = _renderer.render(
    template_name="compaction_instructions.jinja",
    template_variables={},
)


def build_full_system_prompt(
    base_prompt: str,
    role_name: str,
    communication_enabled: bool,
) -> str:
    """Combine an agent prompt with its enabled runtime interaction protocol."""
    template_name = "system_suffix_silent.jinja"
    if communication_enabled:
        template_name = "system_suffix.jinja"
    suffix = _renderer.render(
        template_name=template_name,
        template_variables={"role_name": role_name},
    )
    return base_prompt + "\n\n" + suffix


def continue_prompt_for(communication_enabled: bool) -> str:
    """Return the continuation prompt matching an agent's tool affordances."""
    if communication_enabled:
        return CONTINUE_PROMPT
    return SILENT_CONTINUE_PROMPT
