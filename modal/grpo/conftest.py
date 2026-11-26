"""Leaves out the trainer's tests when torch is not installed.

``test_grpo_training.py`` needs torch, transformers and peft, which the repository's environment
does not install, so ``pytest modal/grpo/`` there runs the loop's tests only. The report header
says so. README.md gives the command that runs the trainer's tests.
"""

import importlib.util

import pytest

TRAINER_TESTS = "test_grpo_training.py"
TORCH_INSTALLED = importlib.util.find_spec("torch") is not None

collect_ignore: list[str] = []
if not TORCH_INSTALLED:
    collect_ignore.append(TRAINER_TESTS)


def pytest_report_header(config: pytest.Config) -> str | None:
    """Name the tests that this environment leaves out."""
    _ = config
    if TORCH_INSTALLED:
        return None
    return f"{TRAINER_TESTS} left out: torch is not installed"
