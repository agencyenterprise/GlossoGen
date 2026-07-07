"""Renders Jinja2 templates for evaluation prompts."""

from pathlib import Path

from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent

_RENDERER = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])


def render_evaluator_prompt(template_name: str, template_variables: dict[str, object]) -> str:
    """Render a named template from the evaluation prompts directory."""
    return _RENDERER.render(template_name=template_name, template_variables=template_variables)
