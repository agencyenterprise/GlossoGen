"""A per-seat launcher that starts the Claude Code CLI without the variables it inherits.

The SDK starts the CLI with the whole parent environment plus the options' own
variables, and offers no way to remove one. The CLI reads many ``CLAUDE*``
variables a pydantic-ai seat never does: ones that send it to another backend
or credential (``CLAUDE_CODE_USE_BEDROCK``, ``CLAUDE_CODE_OAUTH_TOKEN``), and,
when glossogen itself was started from a Claude Code session, that session's
own (``CLAUDE_CODE_SESSION_ID``, ``CLAUDE_CODE_MESSAGING_SOCKET``,
``CLAUDE_EFFORT``). The launcher is a shell script the SDK runs as its CLI; it
removes those variables and starts the bundled binary, so a seat behaves the
same whatever shell launched the run.
"""

import importlib.util
import shlex
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

INHERITED_PREFIX = "CLAUDE"
INHERITED_NAMES = frozenset({"ANTHROPIC_IDENTITY_TOKEN"})
"""Variables outside the ``CLAUDE`` prefix that the CLI reads and a pydantic-ai
Anthropic seat does not; each is a credential other than ``ANTHROPIC_API_KEY``."""
SDK_SET_NAMES = frozenset(
    {"CLAUDE_CODE_ENTRYPOINT", "CLAUDE_AGENT_SDK_VERSION", "CLAUDE_CODE_SDK_READS_SESSION_STATE"}
)
"""Variables the SDK sets on every launch, after the inherited ones."""
SDK_PACKAGE = "claude_agent_sdk"
LAUNCHER_FILE_NAME = "claude_launcher.sh"


def removed_variables(environ: Mapping[str, str], kept: Iterable[str]) -> list[str]:
    """The inherited variables the launcher removes: ``CLAUDE*`` and other CLI credentials.

    ``kept`` names the variables the session sets itself, which stay along with
    the ones the SDK sets.
    """
    keep = set(kept) | SDK_SET_NAMES
    return sorted(
        name
        for name in environ
        if (name.startswith(INHERITED_PREFIX) or name in INHERITED_NAMES) and name not in keep
    )


def bundled_cli_path() -> Path:
    """The Claude Code binary the SDK wheel bundles."""
    spec = importlib.util.find_spec(name=SDK_PACKAGE)
    if spec is None or spec.origin is None:
        raise RuntimeError(f"{SDK_PACKAGE} is not installed")
    cli = Path(spec.origin).parent / "_bundled" / "claude"
    if not cli.is_file():
        raise RuntimeError(f"the {SDK_PACKAGE} wheel bundles no CLI at {cli}")
    return cli


def write_cli_launcher(directory: Path, cli: Path, removed: Sequence[str]) -> Path:
    """Write the launcher into ``directory`` and return its path."""
    unset = " ".join(f"-u {shlex.quote(name)}" for name in removed)
    launcher = directory / LAUNCHER_FILE_NAME
    launcher.write_text(f'#!/bin/sh\nexec env {unset} {shlex.quote(str(cli))} "$@"\n')
    launcher.chmod(0o755)
    return launcher
