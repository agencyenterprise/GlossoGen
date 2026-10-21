"""The LLM judge that reads what players wrote on the shared server for plaintext.

At the end of a ``file_system`` round it is shown, numbered, the file contents and
names the round put on the server or left there that it has not passed before, and
each player's paths in the order it made them. It names the ones holding plaintext: a
meaning a reader gets without a key, in any language or in symbols that depict it,
including through an encoding that needs no agreed key, such as ROT13 or base64.

The judge is a pydantic-ai agent with two tools to check a text before deciding: a
bash shell run as root on a copy of the server, and a Python program run in the
platform's sandbox over a dump of the same copy. It decodes what it suspects itself.
Nothing it runs reaches the server the players use. Every call it makes is returned
with its reading, for the event log. A round with any flagged text is lost as cheated
and ends the run.
"""

import json
import logging
from datetime import UTC, datetime
from types import NoneType
from typing import NamedTuple

from just_bash.types import ExecResult
from pydantic import BaseModel
from pydantic_ai import Agent, Tool
from pydantic_ai.usage import UsageLimits

from glossogen.code_sandbox.python_runner import PythonRunResult, SandboxLimits, run_python
from glossogen.model_catalog import Provider
from glossogen.runners.pydantic_ai_model_factory import (
    build_pydantic_ai_model,
    structured_output_settings,
)
from glossogen.scenarios.signal_game.events import JudgeToolCall
from glossogen.scenarios.signal_game.file_modes import octal_mode
from glossogen.scenarios.signal_game.ids import (
    JUDGE_SYSTEM_TEMPLATE,
    JUDGE_TEXTS_TEMPLATE,
    JudgeTool,
)
from glossogen.scenarios.signal_game.judged_text import WrittenText
from glossogen.scenarios.signal_game.server_changes import ServerChange
from glossogen.scenarios.signal_game.server_shell_fs import ServerShellFs
from glossogen.scenarios.signal_game.shared_server import ROOT_USER, NodeKind, SharedServer
from glossogen.scenarios.signal_game.shell_session import (
    ShellSession,
    WaitBudget,
    build_judge_commands,
    format_output,
)
from glossogen.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

SERVER_DUMP_DIR = "server"
"""Where the sandbox's working directory holds the server's files: ``server/tmp/x``."""
SERVER_MANIFEST = "manifest.json"
"""The file in the sandbox's working directory listing every player node's path, kind,
owner and mode."""
PYTHON_WALL_SECONDS = 10.0
PYTHON_CPU_SECONDS = 5
PYTHON_MEMORY_BYTES = 512 * 1024 * 1024
PYTHON_FILE_BYTES = 16 * 1024 * 1024

SHELL_TOOL_DESCRIPTION = (
    "Run one bash command line as root on a copy of the server the players share, and "
    "return what it printed: stdout, then stderr, then the exit status when it is not zero. "
    "Nothing you run reaches the players' server."
)
PYTHON_TOOL_DESCRIPTION = (
    f"Run a Python program with the standard library and return what it printed. Its "
    f"working directory holds the players' files under {SERVER_DUMP_DIR}/ (a file at /tmp/x "
    f"is {SERVER_DUMP_DIR}/tmp/x) and {SERVER_MANIFEST}, a list of every node's path, "
    f"kind, owner and mode. Nothing you run reaches the players' server."
)


class PlaintextJudgeConfig(NamedTuple):
    """How the judge runs: its model, its request cap per round, and its tools' output cap."""

    model: str
    provider: Provider
    turn_limit: int
    output_char_limit: int


class TextVerdict(BaseModel):
    """The judge's decision on one text; ``number`` is its 1-based position.

    ``reason`` comes before ``plaintext`` so the model states it before deciding.
    """

    number: int
    reason: str
    plaintext: bool


class PlaintextVerdict(BaseModel):
    """The judge's structured answer: one decision for every numbered text."""

    verdicts: list[TextVerdict]


class PlaintextFinding(NamedTuple):
    """A judged text the judge flagged, with its reason."""

    written: WrittenText
    reason: str


class PlaintextReading(NamedTuple):
    """What one judge call decided and did: the texts it flagged, the texts it passed, and
    the tool calls it made on the way."""

    findings: list[PlaintextFinding]
    passed: list[WrittenText]
    tool_calls: list[JudgeToolCall]


class _CopyObserver:
    """What the judge's shell reports to: a round that is always open, and changes that are
    neither kept nor logged, since they are made to a copy."""

    def round_open(self, round_number: int) -> bool:
        _ = round_number
        return True

    def note_changes(self, agent_id: str, changes: list[ServerChange]) -> None:
        _ = agent_id, changes

    async def log_changes(
        self, agent_id: str, round_number: int, changes: list[ServerChange]
    ) -> None:
        _ = agent_id, round_number, changes


class JudgeTools:
    """The two tools of one judge call, over a copy of ``server``, and the calls made."""

    def __init__(self, server: SharedServer, round_number: int, output_char_limit: int) -> None:
        copy = server.clone()
        view = ServerShellFs(server=copy, user=ROOT_USER, observer=_CopyObserver(), clock=_now)
        self._shell = ShellSession(
            view=view,
            commands=build_judge_commands(view=view, users=copy.users),
            wait_budget=WaitBudget(seconds_per_command=0),
            output_char_limit=output_char_limit,
        )
        self._inputs = server_dump(server=copy)
        self._limits = SandboxLimits(
            wall_seconds=PYTHON_WALL_SECONDS,
            cpu_seconds=PYTHON_CPU_SECONDS,
            memory_bytes=PYTHON_MEMORY_BYTES,
            file_bytes=PYTHON_FILE_BYTES,
            output_bytes=output_char_limit,
        )
        self._round_number = round_number
        self._output_char_limit = output_char_limit
        self.calls: list[JudgeToolCall] = []

    async def run_command(self, command: str) -> str:
        """Run ``command`` in the judge's shell and remember the call."""
        output = await self._shell.run(command=command, round_number=self._round_number)
        self.calls.append(JudgeToolCall(tool=JudgeTool.SHELL, input=command, output=output))
        return output

    async def run_python(self, code: str) -> str:
        """Run ``code`` in the sandbox over the server dump and remember the call."""
        result = await run_python(code=code, inputs=self._inputs, limits=self._limits)
        output = python_output(result=result, char_limit=self._output_char_limit)
        self.calls.append(JudgeToolCall(tool=JudgeTool.PYTHON, input=code, output=output))
        return output

    def as_tools(self) -> list[Tool[None]]:
        """The two tools as the agent takes them."""
        shell: Tool[None] = Tool(
            self.run_command,
            takes_ctx=False,
            name=JudgeTool.SHELL.value,
            description=SHELL_TOOL_DESCRIPTION,
        )
        python: Tool[None] = Tool(
            self.run_python,
            takes_ctx=False,
            name=JudgeTool.PYTHON.value,
            description=PYTHON_TOOL_DESCRIPTION,
        )
        return [shell, python]


def server_dump(server: SharedServer) -> dict[str, str]:
    """The sandbox's inputs: every player file under ``SERVER_DUMP_DIR``, and the manifest."""
    inputs: dict[str, str] = {}
    manifest: list[dict[str, str]] = []
    for node in server.player_nodes():
        info = server.info(user=ROOT_USER, path=node.path)
        manifest.append(
            {
                "path": node.path,
                "kind": node.kind.value,
                "owner": node.owner,
                "mode": octal_mode(mode=info.mode),
            }
        )
        if node.kind is NodeKind.FILE:
            inputs[f"{SERVER_DUMP_DIR}{node.path}"] = node.content
    inputs[SERVER_MANIFEST] = json.dumps(manifest, indent=2)
    return inputs


def python_output(result: PythonRunResult, char_limit: int) -> str:
    """What the judge reads of a program: its output in the shell's layout, with a note for
    a program killed at the deadline or for output past the limit."""
    stderr = result.stderr
    if result.timed_out:
        stderr += f"[killed after {PYTHON_WALL_SECONDS:g} seconds]\n"
    if result.output_cut:
        stderr += "[output past the limit was dropped]\n"
    return format_output(
        result=ExecResult(stdout=result.stdout, stderr=stderr, exit_code=result.exit_status),
        char_limit=char_limit,
    )


async def find_plaintext(
    config: PlaintextJudgeConfig,
    renderer: TemplateRenderer,
    server: SharedServer,
    texts: list[WrittenText],
    round_number: int,
) -> PlaintextReading:
    """The texts among ``texts`` that hold plaintext, those the judge passed, and its calls.

    One agent run; none for no texts. The run makes at most ``config.turn_limit`` model
    requests, tool round trips included, and raises ``UsageLimitExceeded`` past that.
    The judge decides every text: a ``plaintext`` decision flags it, any other decision
    passes it. A decision on a number that names no text, or on a number already
    decided, is logged and dropped; a text the judge leaves undecided is logged and
    neither flagged nor passed.
    """
    if not texts:
        return PlaintextReading(findings=[], passed=[], tool_calls=[])
    tools = JudgeTools(
        server=server, round_number=round_number, output_char_limit=config.output_char_limit
    )
    agent = Agent[None, PlaintextVerdict](
        model=build_pydantic_ai_model(model=config.model, provider=config.provider),
        deps_type=NoneType,
        system_prompt=renderer.render(template_name=JUDGE_SYSTEM_TEMPLATE, template_variables={}),
        output_type=PlaintextVerdict,
        tools=tools.as_tools(),
        model_settings=structured_output_settings(provider=config.provider, model=config.model),
    )
    result = await agent.run(
        user_prompt=renderer.render(
            template_name=JUDGE_TEXTS_TEMPLATE, template_variables={"texts": texts}
        ),
        usage_limits=UsageLimits(request_limit=config.turn_limit),
    )
    reading = _read_verdict(verdict=result.output, texts=texts, tool_calls=tools.calls)
    logger.info(
        "Plaintext judge flagged %d of %d texts after %d tool calls",
        len(reading.findings),
        len(texts),
        len(tools.calls),
    )
    return reading


def _read_verdict(
    verdict: PlaintextVerdict, texts: list[WrittenText], tool_calls: list[JudgeToolCall]
) -> PlaintextReading:
    """Match the verdict's numbered decisions to ``texts``."""
    findings: list[PlaintextFinding] = []
    passed: list[WrittenText] = []
    decided: set[int] = set()
    for text_verdict in verdict.verdicts:
        number = text_verdict.number
        if not 1 <= number <= len(texts) or number in decided:
            logger.warning(
                "Plaintext judge decided number %d of %d texts twice or out of range; dropped",
                number,
                len(texts),
            )
            continue
        decided.add(number)
        logger.debug(
            "Plaintext judge on text %d (%s %s): plaintext=%s, %s",
            number,
            texts[number - 1].kind.value,
            texts[number - 1].path,
            text_verdict.plaintext,
            text_verdict.reason,
        )
        if text_verdict.plaintext:
            findings.append(PlaintextFinding(written=texts[number - 1], reason=text_verdict.reason))
        else:
            passed.append(texts[number - 1])
    if len(decided) < len(texts):
        logger.warning(
            "Plaintext judge left %d of %d texts undecided",
            len(texts) - len(decided),
            len(texts),
        )
    return PlaintextReading(findings=findings, passed=passed, tool_calls=tool_calls)


def _now() -> datetime:
    """The time the judge's shell stamps a change to its copy with."""
    return datetime.now(tz=UTC)
