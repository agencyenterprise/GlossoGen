"""Renders Jinja2 templates for Veyru evaluation prompts.

Searches the evaluation prompts directory first, then falls back to the
main Veyru prompts directory so evaluator templates can ``{% include %}``
shared partials defined alongside the live-scenario prompts.
"""

from pathlib import Path

from schmidt.template_renderer import TemplateRenderer

_EVALUATION_PROMPTS_DIR = Path(__file__).parent / "prompts"
_SCENARIO_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

_RENDERER = TemplateRenderer(
    prompts_dirs=[_EVALUATION_PROMPTS_DIR, _SCENARIO_PROMPTS_DIR],
)


def render_veyru_prompt(template_name: str, template_variables: dict[str, object]) -> str:
    """Render a named template from the Veyru evaluation prompts directory."""
    return _RENDERER.render(template_name=template_name, template_variables=template_variables)
