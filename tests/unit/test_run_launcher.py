"""Tests for the config file a launched simulation is handed.

The REST and MCP launch paths build a `glossogen run` command line rather than
calling the runtime directly, so the command has to be one the CLI accepts.
`--config` is required there, which makes writing the file unconditional: a
launcher that skipped it for an empty config would spawn a subprocess that dies
in argparse, and the caller would see a run that never started.
"""

from pathlib import Path
from typing import Any

import orjson

from glossogen.server.run_launcher import build_config_file


def read_back(path: Path) -> dict[str, Any]:
    """Return what the launcher wrote for the subprocess to read."""
    return orjson.loads(path.read_bytes())


def test_knobs_reach_the_subprocess() -> None:
    """The validated knobs are what the file carries."""
    written = build_config_file(knobs={"round_count": 4, "seed": 42})
    assert read_back(written) == {"round_count": 4, "seed": 42}


def test_an_empty_config_still_produces_a_file() -> None:
    """`run` requires --config, so there is always something to point it at.

    The resulting run fails against the scenario's knobs model, which names the
    missing fields, rather than in argparse, which would only say the flag is
    missing on a command the user never typed.
    """
    written = build_config_file(knobs={})
    assert written.is_file()
    assert read_back(written) == {}
