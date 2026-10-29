"""`glossogen serve --ui-port`: the UI container is removed however the server stops.

uvicorn shuts down on SIGTERM and then raises the signal again under whatever
handler was installed before it started. The fake server here does that last
step, so the test covers the path a `kill` takes without starting uvicorn,
Docker or a clock.
"""

import argparse
import signal

import pytest

from glossogen.cli import serve_command
from glossogen.frontend_container import FrontendContainer


def test_sigterm_removes_the_ui_container(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", "")
    monkeypatch.setenv("GLOSSOGEN_RUNS_DIR", "")
    removed: list[str] = []

    def fake_start_frontend_container(
        api_port: int,  # noqa: ARG001 — signature-required
        ui_port: int,
        image: str,  # noqa: ARG001 — signature-required
    ) -> FrontendContainer:
        return FrontendContainer(container_id="ui-container", url=f"http://localhost:{ui_port}")

    def fake_stop_frontend_container(container_id: str) -> None:
        removed.append(container_id)

    def fake_run_uvicorn_stopped_by_kill(port: int) -> None:  # noqa: ARG001 — signature-required
        signal.raise_signal(signal.SIGTERM)

    monkeypatch.setattr(
        target=serve_command,
        name="start_frontend_container",
        value=fake_start_frontend_container,
    )
    monkeypatch.setattr(
        target=serve_command, name="stop_frontend_container", value=fake_stop_frontend_container
    )
    monkeypatch.setattr(
        target=serve_command, name="_run_uvicorn", value=fake_run_uvicorn_stopped_by_kill
    )
    handler_before = signal.getsignal(signal.SIGTERM)

    with pytest.raises(SystemExit) as exit_info:
        serve_command.handle_serve(
            args=argparse.Namespace(runs_dir="runs", port=8000, ui_port=3000, ui_image=None)
        )

    assert removed == ["ui-container"]
    assert exit_info.value.code == 128 + signal.SIGTERM
    assert signal.getsignal(signal.SIGTERM) is handler_before


def test_sigterm_while_the_ui_starts_restores_the_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The handler is in place before the container starts, and gone after."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "")
    monkeypatch.setenv("GLOSSOGEN_RUNS_DIR", "")
    served: list[int] = []

    def fake_start_frontend_container_killed_while_waiting(
        api_port: int,  # noqa: ARG001 — signature-required
        ui_port: int,  # noqa: ARG001 — signature-required
        image: str,  # noqa: ARG001 — signature-required
    ) -> FrontendContainer:
        signal.raise_signal(signal.SIGTERM)
        raise AssertionError("SIGTERM did not interrupt the start")

    monkeypatch.setattr(
        target=serve_command,
        name="start_frontend_container",
        value=fake_start_frontend_container_killed_while_waiting,
    )
    monkeypatch.setattr(target=serve_command, name="_run_uvicorn", value=served.append)
    handler_before = signal.getsignal(signal.SIGTERM)

    with pytest.raises(SystemExit):
        serve_command.handle_serve(
            args=argparse.Namespace(runs_dir="runs", port=8000, ui_port=3000, ui_image=None)
        )

    assert served == []
    assert signal.getsignal(signal.SIGTERM) is handler_before
