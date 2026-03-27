"""Renders PDF export data into a self-contained HTML string via a Jinja2 template.

The rendered HTML is designed for conversion to PDF with weasyprint —
all CSS is inlined and the document is self-contained.
"""

import json
from datetime import datetime
from pathlib import Path

import markdown as md
from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

from schmidt.server.pdf_export_data import HexColor, PdfExportData, derive_initials, get_agent_color

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _markdown_to_html(text: str) -> Markup:
    """Convert markdown text to HTML, returning a Markup-safe string."""
    html = md.markdown(text, extensions=["tables", "fenced_code"])
    return Markup(html)


def _format_time(value: datetime) -> str:
    """Format a datetime as HH:MM."""
    return value.strftime("%H:%M")


def _format_datetime(value: datetime) -> str:
    """Format a datetime as a full human-readable string."""
    return value.strftime("%Y-%m-%d %H:%M:%S UTC")


def _format_json(value: object) -> str:
    """Pretty-print a value as JSON, truncating long strings."""
    if isinstance(value, str):
        if len(value) > 500:
            return value[:500] + "..."
        return value
    return json.dumps(value, indent=2, default=str)


def render_pdf_html(export_data: PdfExportData) -> str:
    """Render the PDF export data into a complete HTML document string."""
    env = Environment(
        loader=FileSystemLoader(_TEMPLATES_DIR),
        autoescape=True,
        keep_trailing_newline=False,
    )
    env.filters["markdown_to_html"] = _markdown_to_html
    env.filters["format_time"] = _format_time
    env.filters["format_datetime"] = _format_datetime
    env.filters["format_json"] = _format_json

    agent_colors: dict[str, HexColor] = {}
    agent_initials: dict[str, str] = {}
    for idx, agent in enumerate(export_data.agents):
        agent_colors[agent.agent_id] = get_agent_color(index=idx)
        agent_initials[agent.agent_id] = derive_initials(role_name=agent.role_name)

    show_channel_badges = export_data.channel_filter is None

    template = env.get_template(name="pdf_export.jinja")
    return template.render(
        data=export_data,
        agent_colors=agent_colors,
        agent_initials=agent_initials,
        show_channel_badges=show_channel_badges,
    )
