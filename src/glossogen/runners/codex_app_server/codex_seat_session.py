"""``SeatSession`` over ``codex app-server``.

The server is started with the features that would add a tool or instructions
of Codex's own switched off, with the developer and user context Codex injects
turned off, with no ``AGENTS.md`` read from the workspace or its ancestors, and
with a model provider that reads ``OPENAI_API_KEY`` from the environment, so
nothing is logged in and no credential is written. The thread carries the
seat's tools as client-defined tools and the platform's system prompt as its
base instructions, so the model sees that prompt, the user turns, and the
seat's tools.

``CODEX_HOME`` is the seat's ``harness_state`` directory, which archives drop.
Codex writes its session rollout there; it is copied to ``transcripts/`` beside
it when the session closes. Reasoning effort and summaries match the
pydantic-ai runner's OpenAI settings.

A thread cannot be continued in a new server: the app server sends raw response
events only on the thread/start that asked for them, and neither thread/resume
nor thread/fork accepts the flag, so a continued thread's responses could not be
logged. A seat whose server died therefore stops instead.
"""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from glossogen.runners.agent_tools import serialize_tool_result
from glossogen.runners.codex_app_server.app_server_connection import (
    AppServerConnection,
    AppServerExited,
    ServerNotification,
)
from glossogen.runners.codex_app_server.codex_item_translator import CodexItemTranslator
from glossogen.runners.harness_names import HARNESS_STATE_DIR_NAME
from glossogen.runners.session_harness.seat_session import (
    CycleEnded,
    SeatOptions,
    SeatTool,
    SessionItem,
    SessionStarted,
)
from glossogen.runners.session_harness.session_transcripts import keep_session_transcripts

logger = logging.getLogger(__name__)

MODEL_PROVIDER_ID = "glossogen_openai"
TOOL_CALL_METHOD = "item/tool/call"
REASONING_EFFORT = "high"
REASONING_SUMMARY = "concise"
CLIENT_NAME = "glossogen"
CLIENT_VERSION = "1"

CONFIG_OVERRIDES: tuple[str, ...] = (
    f'model_provider="{MODEL_PROVIDER_ID}"',
    (
        f"model_providers.{MODEL_PROVIDER_ID}="
        '{name="OpenAI",base_url="https://api.openai.com/v1",env_key="OPENAI_API_KEY",'
        'wire_api="responses"}'
    ),
    'web_search="disabled"',
    'approval_policy="never"',
    'sandbox_mode="read-only"',
    "check_for_update_on_startup=false",
    "include_permissions_instructions=false",
    "include_environment_context=false",
    "include_apps_instructions=false",
    "include_collaboration_mode_instructions=false",
    "skills.include_instructions=false",
    "project_doc_max_bytes=0",
    "analytics.enabled=false",
    "feedback.enabled=false",
    "tools.experimental_request_user_input={enabled=false}",
)
"""``-c`` overrides: the provider, no web search, no approvals, a read-only
sandbox, none of Codex's own instructions, no ``AGENTS.md``, and no telemetry.
The seat's workspace sits under the run directory, which may be inside a
repository whose ``AGENTS.md`` Codex would otherwise read."""

DISABLED_FEATURES: tuple[str, ...] = (
    "shell_tool",
    "unified_exec",
    "apps",
    "browser_use",
    "browser_use_external",
    "computer_use",
    "image_generation",
    "in_app_browser",
    "multi_agent",
    "plugins",
    "view_image",
    "goals",
    "hooks",
    "skill_search",
    "tool_suggest",
    "shell_snapshot",
    "workspace_dependencies",
    "personality",
    "skill_mcp_dependency_install",
    "remote_plugin",
    "plugin_sharing",
    "code_mode_host",
    "auth_elicitation",
    "tool_call_mcp_elicitation",
)
"""Features that would give the model a tool or a prompt of Codex's own."""


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _ThreadRef(_Lenient):
    id: str


class _ThreadResult(_Lenient):
    thread: _ThreadRef


class _TurnRef(_Lenient):
    id: str


class _TurnResult(_Lenient):
    turn: _TurnRef


class _Ignored(_Lenient):
    pass


class _ToolOutputText(BaseModel):
    type: str
    text: str


class _DynamicToolCallResponse(BaseModel):
    """The app server's ``DynamicToolCallResponse``: the call's output and whether it failed."""

    content_items: list[_ToolOutputText] = Field(serialization_alias="contentItems")
    success: bool


class CodexThreadNotResumable(RuntimeError):
    """A seat's thread was asked to continue in a new app server, which cannot log it."""


class CodexSeatSession:
    """One seat's thread on its own ``codex app-server`` process.

    ``launch_command`` starts the server binary; ``app-server`` and the
    restriction flags are appended to it.
    """

    def __init__(self, launch_command: tuple[str, ...]) -> None:
        self._launch_command = launch_command
        self._items: asyncio.Queue[SessionItem | AppServerExited] = asyncio.Queue()
        self._translator = CodexItemTranslator()
        self._connection: AppServerConnection | None = None
        self._tools: dict[str, SeatTool] = {}
        self._thread_id = ""
        self._turn_id = ""
        self._seat_dir: Path | None = None

    async def connect(self, options: SeatOptions) -> None:
        """Start the server and the seat's thread; the server is closed if either fails."""
        if options.resume_session_id is not None:
            raise CodexThreadNotResumable(
                f"thread {options.resume_session_id} cannot continue in a new codex app "
                "server: a continued thread sends no raw response events, so its responses "
                "could not be logged"
            )
        state_dir = options.seat_dir / HARNESS_STATE_DIR_NAME
        codex_home = state_dir / "codex_home"
        workspace = state_dir / "workspace"
        codex_home.mkdir(parents=True, exist_ok=True)
        workspace.mkdir(parents=True, exist_ok=True)
        self._seat_dir = options.seat_dir
        self._tools = {tool.name: tool for tool in options.tools}
        connection = AppServerConnection(
            on_notification=self._on_notification,
            on_server_request=self._on_server_request,
            on_exit=self._on_exit,
        )
        env = dict(os.environ)
        env["CODEX_HOME"] = str(codex_home)
        await connection.start(command=self._command(), env=env, cwd=workspace)
        self._connection = connection
        try:
            await connection.request(
                method="initialize",
                params={
                    "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
                    "capabilities": {"experimentalApi": True},
                },
                result_model=_Ignored,
            )
            await connection.notify(method="initialized", params={})
            thread = await self._start_thread(
                connection=connection, options=options, workspace=workspace
            )
        except BaseException:
            logger.exception("The codex app server failed to open the seat's thread")
            self._connection = None
            await connection.close()
            raise
        self._thread_id = thread.thread.id
        self._items.put_nowait(SessionStarted(session_id=self._thread_id))

    async def send(self, prompt: str) -> None:
        """Start a turn with ``prompt`` as its user message."""
        result = await self._connected().request(
            method="turn/start",
            params={
                "threadId": self._thread_id,
                "input": [{"type": "text", "text": prompt}],
                "effort": REASONING_EFFORT,
                "summary": REASONING_SUMMARY,
            },
            result_model=_TurnResult,
        )
        self._turn_id = result.turn.id

    async def items(self) -> AsyncIterator[SessionItem]:
        """What the server reports for the turn just started, ending with ``CycleEnded``."""
        while True:
            item = await self._items.get()
            if isinstance(item, AppServerExited):
                raise item
            yield item
            if isinstance(item, CycleEnded):
                return

    async def interrupt(self) -> None:
        """Stop the turn in progress; the server still ends it with ``turn/completed``."""
        await self._connected().request(
            method="turn/interrupt",
            params={"threadId": self._thread_id, "turnId": self._turn_id},
            result_model=_Ignored,
        )

    async def close(self) -> None:
        """End the server and keep the session's rollout with the run."""
        connection = self._connection
        self._connection = None
        try:
            if connection is not None:
                await connection.close()
        finally:
            if self._seat_dir is not None:
                await asyncio.to_thread(
                    keep_session_transcripts,
                    seat_dir=self._seat_dir,
                    source_dir=self._seat_dir / HARNESS_STATE_DIR_NAME / "codex_home" / "sessions",
                )

    def _command(self) -> list[str]:
        command = [*self._launch_command, "app-server"]
        for override in CONFIG_OVERRIDES:
            command.extend(["-c", override])
        for feature in DISABLED_FEATURES:
            command.extend(["--disable", feature])
        return command

    async def _start_thread(
        self, connection: AppServerConnection, options: SeatOptions, workspace: Path
    ) -> _ThreadResult:
        return await connection.request(
            method="thread/start",
            params={
                "model": options.model,
                "baseInstructions": options.system_prompt,
                "cwd": str(workspace),
                "approvalPolicy": "never",
                "sandbox": "read-only",
                "experimentalRawEvents": True,
                "dynamicTools": [
                    {
                        "type": "function",
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.input_schema,
                    }
                    for tool in options.tools
                ],
            },
            result_model=_ThreadResult,
        )

    def _connected(self) -> AppServerConnection:
        if self._connection is None:
            raise RuntimeError("the seat session is not connected")
        return self._connection

    def _on_notification(self, notification: ServerNotification) -> None:
        for item in self._translator.translate(notification=notification):
            self._items.put_nowait(item)

    def _on_exit(self, reason: str) -> None:
        if self._connection is not None:
            self._items.put_nowait(AppServerExited(f"the codex app server stopped: {reason}"))

    async def _on_server_request(
        self, method: str, params: dict[str, Any]
    ) -> _DynamicToolCallResponse:
        """Run a client-defined tool call."""
        if method != TOOL_CALL_METHOD:
            raise ValueError(f"{method} is not supported by this client")
        name = str(params.get("tool"))
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(f"no tool named {name}")
        arguments: dict[str, Any] = {}
        raw_arguments: object = params.get("arguments")
        if isinstance(raw_arguments, dict):
            arguments = dict(cast(dict[str, Any], raw_arguments))
        outcome = await tool.handler(arguments)
        return _DynamicToolCallResponse(
            content_items=[
                _ToolOutputText(
                    type="inputText", text=serialize_tool_result(content=outcome.content)
                )
            ],
            success=not outcome.is_error,
        )
