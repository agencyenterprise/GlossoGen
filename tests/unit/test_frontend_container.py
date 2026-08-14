"""Tests for the frontend container `glossogen serve --ui-port` starts.

What is checked here is the wiring a caller cannot see: the image tag tracks the
installed version rather than drifting to whatever `latest` points at, the run
command names the platform on a host the published images were not built for,
and the UI's origin reaches the CORS list. That last one fails silently in the
browser: every page renders and each request behind it is refused, which reads
as a run list with nothing in it.

Nothing here starts a container. The command is built and asserted on.
"""

import os

import pytest

from glossogen.frontend_container import (
    FRONTEND_IMAGE_REPOSITORY,
    allow_ui_origin,
    build_run_command,
    container_name,
    default_frontend_image,
    lacks_manifest_for_this_host,
)


def test_default_image_is_the_latest_published_one() -> None:
    """Not a tag derived from the installed version.

    Deriving one fails outright between a version bump and the release that
    publishes an image for it, and for any install tracking a branch. Pinning is
    what `--ui-image` is for.
    """
    repository, tag = default_frontend_image().rsplit(":", 1)
    assert repository == FRONTEND_IMAGE_REPOSITORY
    assert tag == "latest"


def test_run_command_wires_the_browser_facing_api_url() -> None:
    """`API_URL` is the backend's host port, since the browser is what calls it."""
    command = build_run_command(
        api_port=8000, ui_port=3000, image="frontend:test", force_amd64=False
    )
    assert "API_URL=http://localhost:8000" in command
    assert "3000:3000" in command
    assert command[-1] == "frontend:test"
    # Detached and self-removing: the CLI holds the id and deletes it on exit.
    assert "--detach" in command
    assert "--rm" in command


def test_run_command_names_the_container_after_its_port() -> None:
    """A deterministic name is what lets a later start clear a leaked container.

    A server killed rather than interrupted never runs its cleanup, so the next
    one removes this name before binding the port again.
    """
    command = build_run_command(
        api_port=8000, ui_port=3010, image="frontend:test", force_amd64=False
    )
    assert command[command.index("--name") + 1] == container_name(ui_port=3010)
    assert container_name(ui_port=3010) != container_name(ui_port=3020)


def test_run_command_takes_the_host_architecture_by_default() -> None:
    """A multi-architecture image resolves to the host's own, so nothing is named."""
    command = build_run_command(
        api_port=8000, ui_port=3000, image="frontend:test", force_amd64=False
    )
    assert "--platform" not in command


def test_run_command_can_name_amd64_for_an_older_release() -> None:
    """Releases published before arm64 manifests existed run under emulation."""
    command = build_run_command(
        api_port=8000, ui_port=3000, image="frontend:test", force_amd64=True
    )
    assert command[command.index("--platform") + 1] == "linux/amd64"


def test_a_missing_manifest_is_what_triggers_the_amd64_retry() -> None:
    """Only Docker's no-such-architecture refusal falls back; other failures do not.

    Retrying every failure under emulation would turn an occupied port or a
    missing tag into a second slow attempt with the same outcome.
    """
    assert lacks_manifest_for_this_host(
        stderr="no matching manifest for linux/arm64/v8 in the manifest list entries"
    )
    assert not lacks_manifest_for_this_host(
        stderr="Bind for 0.0.0.0:3000 failed: port is already allocated"
    )


def test_ui_origin_is_added_to_an_empty_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    """With nothing configured, the UI's own origin is what the backend allows."""
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    allow_ui_origin(ui_port=3010)
    assert os.environ["ALLOWED_ORIGINS"] == "http://localhost:3010"


def test_ui_origin_is_appended_rather_than_replacing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A configured origin survives: the UI's is added to it, not written over it."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example.com")
    allow_ui_origin(ui_port=3010)
    assert os.environ["ALLOWED_ORIGINS"] == "https://app.example.com,http://localhost:3010"


def test_ui_origin_is_not_duplicated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Already listed is already allowed, so the list is left alone."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3010")
    allow_ui_origin(ui_port=3010)
    assert os.environ["ALLOWED_ORIGINS"] == "http://localhost:3010"
