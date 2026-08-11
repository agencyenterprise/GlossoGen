"""Rendering a prompt with a name nobody passed has to fail, not blank out.

Jinja's default `Undefined` renders a missing name as the empty string and
treats it as falsey in a condition. For a prompt that means a budget line with
no number, or a whole `{% if %}` block quietly gone, in text that still looks
like a valid prompt. The run then completes and produces numbers measured
against instructions the agents never received, which is unrecoverable after
the fact because nothing recorded that anything was missing.
"""

from pathlib import Path

import pytest
from jinja2 import UndefinedError

from glossogen.template_renderer import TemplateRenderer


def write_template(tmp_path: Path, body: str) -> TemplateRenderer:
    """Write one template into a fresh prompts dir and return a renderer for it."""
    (tmp_path / "prompt.jinja").write_text(body)
    return TemplateRenderer(prompts_dirs=[tmp_path])


def test_a_misspelled_variable_raises(tmp_path: Path) -> None:
    """The typo is in the template; the caller passed the name it meant to."""
    renderer = write_template(tmp_path, "budget: {{ time_budget_seconds }}")

    with pytest.raises(UndefinedError):
        renderer.render(
            template_name="prompt.jinja",
            template_variables={"time_budget_secondz": 200},
        )


def test_a_missing_name_in_a_condition_raises(tmp_path: Path) -> None:
    """The permissive default drops the block, which is the worse failure.

    A missing number is at least visible in the rendered prompt. A dropped
    `{% if %}` leaves no trace of the instructions it was carrying.
    """
    renderer = write_template(tmp_path, "{% if postmortem_enabled %}discuss afterwards{% endif %}")

    with pytest.raises(UndefinedError):
        renderer.render(template_name="prompt.jinja", template_variables={})


def test_a_missing_attribute_on_a_supplied_object_raises(tmp_path: Path) -> None:
    """Passing the right name with the wrong shape fails the same way.

    Scenarios hand whole outcome objects to their injection templates, so a
    renamed field is as likely as a renamed variable.
    """
    renderer = write_template(tmp_path, "result: {{ outcome.stabilised }}")

    class Outcome:
        """Carries the field under its actual spelling."""

        stabilized = True

    with pytest.raises(UndefinedError):
        renderer.render(
            template_name="prompt.jinja",
            template_variables={"outcome": Outcome()},
        )


def test_supplying_every_name_renders(tmp_path: Path) -> None:
    """Strictness only rejects names the caller never passed."""
    renderer = write_template(
        tmp_path,
        "budget: {{ time_budget_seconds }}{% if postmortem_enabled %} (debrief follows){% endif %}",
    )

    rendered = renderer.render(
        template_name="prompt.jinja",
        template_variables={"time_budget_seconds": 200, "postmortem_enabled": True},
    )

    assert rendered == "budget: 200 (debrief follows)"


def test_a_name_supplied_as_none_still_renders(tmp_path: Path) -> None:
    """`None` is a value the caller chose, unlike a name it never mentioned.

    Injection templates rely on this for the first round, where there is no
    previous outcome to describe yet.
    """
    renderer = write_template(
        tmp_path, "{% if previous_outcome %}last time: {{ previous_outcome }}{% endif %}ready"
    )

    rendered = renderer.render(
        template_name="prompt.jinja",
        template_variables={"previous_outcome": None},
    )

    assert rendered == "ready"
