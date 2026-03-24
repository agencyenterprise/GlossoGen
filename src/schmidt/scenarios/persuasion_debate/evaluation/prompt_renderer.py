"""Renders Jinja2 templates for persuasion debate evaluation prompts."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_JINJA_ENV = Environment(
    loader=FileSystemLoader(_PROMPTS_DIR),
    autoescape=False,
    keep_trailing_newline=False,
)


def render_persuasion_prompt(template_name: str, **kwargs: object) -> str:
    """Render a named template from the persuasion debate evaluation prompts directory."""
    template = _JINJA_ENV.get_template(name=template_name)
    return template.render(**kwargs).strip()
