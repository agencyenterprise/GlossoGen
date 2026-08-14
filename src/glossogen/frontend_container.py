"""Run the published frontend image beside a locally started backend.

The web UI is a Node process and is not part of this Python package, so a
`glossogen serve` that offers one starts the published image. This module owns
that container: the image name for the installed version, the flags the run
needs, the readiness check, and the removal on exit.

Everything the browser fetches goes to the backend directly, so the container
needs no route to the host. It only needs `API_URL` set to the address the
browser reaches the backend on.
"""

import logging
import os
import shutil
import subprocess
import time
from typing import NamedTuple

import httpx

logger = logging.getLogger(__name__)

FRONTEND_IMAGE_REPOSITORY = "ghcr.io/agencyenterprise/glossogen-frontend"

# The port the image listens on inside the container, fixed by its own PORT
# default. The host port is the caller's choice.
_CONTAINER_PORT = 3000

_READINESS_TIMEOUT_SECONDS = 90.0
_READINESS_POLL_SECONDS = 1.0


class FrontendContainer(NamedTuple):
    """A running frontend container and the URL it answers on."""

    container_id: str
    url: str


def default_frontend_image() -> str:
    """Return the published frontend image to run.

    ``latest`` rather than a tag derived from the installed version: the UI is a
    viewer of an API, and deriving the tag makes the flag fail outright between a
    version bump and the release that publishes an image for it. It also fails
    for an install tracking a branch, where no image exists for the commit.

    Pass ``--ui-image`` with a version tag to pin one, which is what an old
    backend needs: a current UI calls endpoints that a much older server does not
    serve.
    """
    return f"{FRONTEND_IMAGE_REPOSITORY}:latest"


def allow_ui_origin(ui_port: int) -> None:
    """Add the UI's origin to ``ALLOWED_ORIGINS`` before the app reads it.

    The server builds its CORS middleware from that variable at import, and
    every API call the UI makes comes from the browser. Without its origin
    listed, the pages render and each request behind them is refused, which
    reads as an empty run list rather than as an error.

    Appends rather than replaces, so a deployment that already lists an origin
    keeps it.
    """
    origin = f"http://localhost:{ui_port}"
    configured = [
        entry.strip() for entry in os.environ.get("ALLOWED_ORIGINS", "").split(",") if entry.strip()
    ]
    if origin in configured:
        return
    os.environ["ALLOWED_ORIGINS"] = ",".join([*configured, origin])


def start_frontend_container(api_port: int, ui_port: int, image: str) -> FrontendContainer:
    """Start the frontend image against a backend on ``api_port``.

    Raises ``RuntimeError`` when Docker is missing, the image cannot be run, or
    the container does not answer within the readiness timeout. Failing here
    rather than carrying on leaves a backend running alone, which reads as a
    working setup until the browser is pointed at a port nothing listens on.
    """
    if shutil.which("docker") is None:
        raise RuntimeError(
            "docker was not found on PATH, and the web UI ships as a container "
            "image. Install Docker, or run the frontend from a glossogen "
            "checkout: cd frontend && npm ci && "
            f"API_URL=http://localhost:{api_port} npm run dev"
        )

    # A CLI killed rather than interrupted never reaches its cleanup, and the
    # container it left holds the port this one wants. Removing the previous
    # occupant of the name makes that a non-event instead of a failed start
    # whose cause is a process that no longer exists.
    _remove_named_container(name=container_name(ui_port=ui_port))

    result = _run_image(api_port=api_port, ui_port=ui_port, image=image, force_amd64=False)
    if result.returncode != 0 and lacks_manifest_for_this_host(stderr=result.stderr):
        # Releases before multi-architecture publishing carry an amd64 manifest
        # only, and this host is not amd64. Emulation is slower than a native
        # image and is why the retry is a fallback rather than the default.
        logger.info(
            "%s has no image for this architecture; retrying under linux/amd64 emulation",
            image,
        )
        result = _run_image(api_port=api_port, ui_port=ui_port, image=image, force_amd64=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Could not start the frontend image {image}: {result.stderr.strip()}\n"
            f"If something else holds port {ui_port}, pass a different --ui-port."
        )

    container_id = result.stdout.strip()
    url = f"http://localhost:{ui_port}"
    _wait_until_ready(container_id=container_id, url=url)
    return FrontendContainer(container_id=container_id, url=url)


def stop_frontend_container(container_id: str) -> None:
    """Remove the container, logging rather than raising if it is already gone."""
    result = subprocess.run(
        ["docker", "rm", "--force", container_id],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logger.warning("Could not remove frontend container: %s", result.stderr.strip())
        return
    logger.info("Frontend container removed")


def _run_image(
    api_port: int, ui_port: int, image: str, force_amd64: bool
) -> subprocess.CompletedProcess[str]:
    """Run the image once, returning the attempt rather than raising on failure."""
    command = build_run_command(
        api_port=api_port, ui_port=ui_port, image=image, force_amd64=force_amd64
    )
    logger.info("Starting frontend container: %s", " ".join(command))
    return subprocess.run(command, capture_output=True, text=True, check=False)


def lacks_manifest_for_this_host(stderr: str) -> bool:
    """Return whether Docker refused the image for want of this architecture."""
    return "no matching manifest" in stderr.lower()


def container_name(ui_port: int) -> str:
    """Return the container's name, derived from the port it publishes.

    Deterministic so a later start can clear a container an earlier one left
    behind. Two servers on different UI ports name different containers.
    """
    return f"glossogen-ui-{ui_port}"


def build_run_command(api_port: int, ui_port: int, image: str, force_amd64: bool) -> list[str]:
    """Build the ``docker run`` argument list.

    ``force_amd64`` names the platform, for an image published before this
    project built arm64 manifests. Left False the host's own architecture is
    used, which is what a multi-architecture image resolves to.
    """
    command = ["docker", "run", "--detach", "--rm"]
    if force_amd64:
        command.extend(["--platform", "linux/amd64"])
    command.extend(
        [
            "--name",
            container_name(ui_port=ui_port),
            "--publish",
            f"{ui_port}:{_CONTAINER_PORT}",
            # Read at request time and handed to the browser, so this is the
            # address the browser reaches the backend on, not one resolvable
            # inside the container.
            "--env",
            f"API_URL=http://localhost:{api_port}",
            "--env",
            f"PORT={_CONTAINER_PORT}",
            image,
        ]
    )
    return command


def _remove_named_container(name: str) -> None:
    """Remove a container by name, saying nothing when there is none.

    ``docker rm --force`` exits 0 whether or not the container existed, and
    reports a removal by naming it on stdout. The exit code alone would announce
    a cleanup on every clean start.
    """
    result = subprocess.run(
        ["docker", "rm", "--force", name],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stdout.strip():
        logger.info("Removed a frontend container left by an earlier server: %s", name)


def _wait_until_ready(container_id: str, url: str) -> None:
    """Poll the container until it serves, or raise with what it logged.

    A container that exits on startup (a bad image, an occupied port) would
    otherwise leave the CLI printing a URL that answers nothing.
    """
    deadline = time.monotonic() + _READINESS_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if not _is_running(container_id=container_id):
            logs = _container_logs(container_id=container_id)
            raise RuntimeError(f"The frontend container exited during startup:\n{logs}")
        try:
            response = httpx.get(url, timeout=5.0)
        except httpx.HTTPError:
            time.sleep(_READINESS_POLL_SECONDS)
            continue
        if response.status_code < 500:
            logger.info("Frontend ready at %s", url)
            return
        time.sleep(_READINESS_POLL_SECONDS)

    logs = _container_logs(container_id=container_id)
    stop_frontend_container(container_id=container_id)
    raise RuntimeError(
        f"The frontend container did not answer on {url} within "
        f"{_READINESS_TIMEOUT_SECONDS:.0f}s:\n{logs}"
    )


def _is_running(container_id: str) -> bool:
    """Return whether the container is still up."""
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", container_id],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() == "true"


def _container_logs(container_id: str) -> str:
    """Return the container's output, for an error message that says why."""
    result = subprocess.run(
        ["docker", "logs", "--tail", "20", container_id],
        capture_output=True,
        text=True,
        check=False,
    )
    return f"{result.stdout}{result.stderr}".strip()
