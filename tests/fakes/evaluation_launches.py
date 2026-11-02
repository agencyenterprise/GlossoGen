"""A recorder that stands in for ``subprocess.Popen`` inside the runs router.

The evaluate endpoint launches ``python -m glossogen evaluate`` when it accepts a
request. With the recorder in place nothing is launched, whatever the endpoint
decides, and each launch it attempted is kept for the test to read. Every
recorded launch reports the same ``pid``, which the test's process table decides
is alive or not.
"""

from typing import IO, NamedTuple

import pytest

from glossogen.server.runs import router as runs_router_module


class RecordedLaunch(NamedTuple):
    """One process the evaluate endpoint tried to start."""

    command: list[str]
    stdout_path: str
    start_new_session: bool


def record_evaluation_launches(monkeypatch: pytest.MonkeyPatch, pid: int) -> list[RecordedLaunch]:
    """Replace the router's ``subprocess.Popen`` and return the list it appends to.

    The stand-in process never runs, so it never writes the evaluation manifest
    the real ``glossogen evaluate`` writes once it has started up.
    """
    recorded: list[RecordedLaunch] = []

    class RecordingPopen:
        """Records its arguments instead of starting a process."""

        def __init__(
            self, args: list[str], stdout: IO[str], start_new_session: bool, **kwargs: object
        ) -> None:
            _ = kwargs
            self.pid = pid
            recorded.append(
                RecordedLaunch(
                    command=list(args),
                    stdout_path=stdout.name,
                    start_new_session=start_new_session,
                )
            )

    monkeypatch.setattr(runs_router_module.subprocess, "Popen", RecordingPopen)
    return recorded
