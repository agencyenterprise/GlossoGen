"""Renders Jinja2 templates for evaluation prompts."""

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

_JINJA_ENV = Environment(
    loader=FileSystemLoader(str(PROMPTS_DIR)),
    autoescape=False,
    keep_trailing_newline=False,
)


def render_evaluator_prompt(template_name: str, **kwargs: object) -> str:
    """Render a named template from the evaluation prompts directory."""
    template = _JINJA_ENV.get_template(name=template_name)
    return template.render(**kwargs).strip()
