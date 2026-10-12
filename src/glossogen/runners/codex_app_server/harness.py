"""The ``codex`` harness: drives seats through the Codex CLI's app server.

The Codex binary is the optional ``harness-codex`` extra, which installs
``openai-codex-cli-bin``. The launch check refuses a seat under this harness when
the extra is missing or the seat's provider is not OpenAI, and the binary's
package is imported by name only when a runner is built, so the platform
imports cleanly without the extra.
"""

import importlib
import importlib.util
from pathlib import Path
from typing import cast

from glossogen.model_catalog import Provider
from glossogen.runners.codex_app_server.codex_seat_session import CodexSeatSession
from glossogen.runners.harness_names import CODEX_HARNESS_NAME
from glossogen.runners.harness_protocol import AgentHarness, HarnessSeat, RunnerBuildContext
from glossogen.runners.session_harness.runner import SessionSeatRunner

BINARY_MODULE = "codex_cli_bin"
BINARY_EXTRA = "harness-codex"


class CodexAppServerHarness(AgentHarness):
    """Builds ``SessionSeatRunner`` instances over a ``codex app-server`` per seat."""

    @classmethod
    def name(cls) -> str:
        return CODEX_HARNESS_NAME

    @classmethod
    def gates_model_responses(cls) -> bool:
        return False

    @classmethod
    def preflight(cls, seats: tuple[HarnessSeat, ...]) -> tuple[str, ...]:
        remedies: list[str] = []
        if importlib.util.find_spec(name=BINARY_MODULE) is None:
            remedies.append(
                f"install the {BINARY_EXTRA} extra: make install-server in a checkout, "
                f"or depend on glossogen[{BINARY_EXTRA}]"
            )
        other_providers = sorted({seat.provider.value for seat in seats} - {Provider.OPENAI})
        if other_providers:
            remedies.append(
                f"run these seats under provider {Provider.OPENAI.value}; Codex drives "
                f"OpenAI models only, not {', '.join(other_providers)}"
            )
        return tuple(remedies)

    @classmethod
    def build_runner(cls, context: RunnerBuildContext) -> SessionSeatRunner:
        binary_package = importlib.import_module(name=BINARY_MODULE)
        binary = cast(Path, binary_package.bundled_codex_path())
        launch_command = (str(binary),)

        def new_session() -> CodexSeatSession:
            return CodexSeatSession(launch_command=launch_command)

        return SessionSeatRunner(
            context=context, session_factory=new_session, harness_name=CODEX_HARNESS_NAME
        )
