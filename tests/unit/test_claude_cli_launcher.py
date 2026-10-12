"""The launcher that starts Claude Code without the variables the SDK hands it from this process."""

import subprocess
from pathlib import Path

from glossogen.runners.claude_agent_sdk.cli_launcher import removed_variables, write_cli_launcher

PARENT_SESSION_ENV = {
    "CLAUDE_CODE_SESSION_ID": "parent-session",
    "CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/parent.sock",
    "CLAUDE_EFFORT": "high",
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "CLAUDE_CODE_OAUTH_TOKEN": "oauth",
    "ANTHROPIC_IDENTITY_TOKEN": "identity",
}


def test_the_parent_sessions_and_credential_variables_are_removed_and_the_seats_kept() -> None:
    environ = {
        **PARENT_SESSION_ENV,
        "CLAUDE_CONFIG_DIR": "/seat/claude_config",
        "CLAUDE_CODE_ENTRYPOINT": "sdk-py",
        "ANTHROPIC_API_KEY": "sk-ant",
        "ANTHROPIC_BASE_URL": "https://proxy.example",
        "PATH": "/usr/bin",
    }

    removed = removed_variables(environ=environ, kept={"CLAUDE_CONFIG_DIR"})

    assert removed == sorted(PARENT_SESSION_ENV)


def test_the_launcher_starts_the_cli_without_the_removed_variables(tmp_path: Path) -> None:
    """A stand-in CLI prints its environment, which is what the real one would read."""
    fake_cli = tmp_path / "fake claude"
    fake_cli.write_text('#!/bin/sh\necho "args=$*"\nenv\n')
    fake_cli.chmod(0o755)
    launcher = write_cli_launcher(
        directory=tmp_path, cli=fake_cli, removed=sorted(PARENT_SESSION_ENV)
    )

    completed = subprocess.run(
        [str(launcher), "--print", "hello world"],
        env={**PARENT_SESSION_ENV, "CLAUDE_CONFIG_DIR": "/seat", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )

    lines = completed.stdout.splitlines()
    assert lines[0] == "args=--print hello world"
    names = {line.split("=", 1)[0] for line in lines[1:]}
    assert "CLAUDE_CONFIG_DIR" in names
    assert not names & set(PARENT_SESSION_ENV)
