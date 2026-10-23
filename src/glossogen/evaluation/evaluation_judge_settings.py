"""The settings the ``evaluate`` judge is sent with, read from ``--judge-settings``.

``evaluate`` picks its judge with its own flags rather than the run's knobs, since
one run is evaluated many times and under different judges, so its settings are a
flag too. The value is a ``JudgeModelSettings`` object as JSON.
"""

import argparse
import json

from glossogen.models.agent_model_settings import JudgeModelSettings


def add_judge_settings_argument(parser: argparse.ArgumentParser) -> None:
    """Add ``--judge-settings`` to ``parser``."""
    parser.add_argument(
        "--judge-settings",
        dest="judge_settings",
        type=str,
        default=None,
        help=(
            "Model settings sent with every judge call, as a JSON object with the "
            "fields of the agent_model_settings knob, e.g. "
            '\'{"max_tokens": 65536, "thinking": "low"}\'. '
            "A setting left out is not sent, the output cap included."
        ),
    )


def parse_judge_settings(raw: str | None) -> JudgeModelSettings:
    """Return the judge settings ``raw`` spells; none when it is ``None``.

    Raises ValueError when ``raw`` is not a JSON object of known settings.
    """
    if raw is None:
        return JudgeModelSettings()
    given: object = json.loads(raw)
    if not isinstance(given, dict):
        raise ValueError(f"--judge-settings must be a JSON object, got {raw!r}")
    return JudgeModelSettings.model_validate(given)
