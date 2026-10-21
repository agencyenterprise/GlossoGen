"""The LLM judge that reads what players wrote on the shared server for plaintext.

At the end of a ``file_system`` round it is shown the server's tree and, numbered, the
file contents and names the round put on the server or left there that it has not
passed before. It names the ones holding plaintext: a meaning a reader gets without a
key, in any language or in symbols that depict it, including through an encoding that
needs no agreed key, such as ROT13 or base64.

The judge is a pydantic-ai agent with two tools to check a text before deciding: a
bash shell run as root in a container of its own, started from the round-end snapshot
and removed after the call, and a Python program run in the platform's sandbox over a
dump of the same snapshot. It decodes what it suspects itself, and nothing it runs
reaches the players' server. Every call it makes is returned with its reading, for
the event log. A round with any flagged text is lost as cheated and ends the run.
"""

import json
import logging
from types import NoneType
from typing import NamedTuple

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
from glossogen.scenarios.signal_game.ids import (
    JUDGE_SYSTEM_TEMPLATE,
    JUDGE_TEXTS_TEMPLATE,
    JudgeTool,
    WrittenTextKind,
)
from glossogen.scenarios.signal_game.judged_text import WrittenText
from glossogen.scenarios.signal_game.player_shell import format_output
from glossogen.scenarios.signal_game.server_activity import name_text
from glossogen.scenarios.signal_game.server_container import ExecOutput, ServerContainer
from glossogen.scenarios.signal_game.server_snapshot import MODE_MASK, NodeKind, ServerSnapshot
from glossogen.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

SERVER_DUMP_DIR = "server"
"""Where the sandbox's working directory holds the server's files: ``server/tmp/x``."""
SERVER_MANIFEST = "manifest.json"
"""The file in the sandbox's working directory listing every player node's path, kind,
owner and mode."""
JUDGE_COMMAND_SECONDS = 30.0
PYTHON_WALL_SECONDS = 10.0
PYTHON_CPU_SECONDS = 5
PYTHON_MEMORY_BYTES = 512 * 1024 * 1024
PYTHON_FILE_BYTES = 16 * 1024 * 1024

SHELL_TOOL_DESCRIPTION = (
    "Run one bash command line as root on a copy of the server the players share, as it "
    "stood when the round ended, and return what it printed: stdout, then stderr, then the "
    "exit status when it is not zero. Nothing you run reaches the players' server."
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


class TreeFinding(BaseModel):
    """A path from the tree the judge flags that is not among the numbered texts, such as
    one of the names a word is spelled across; ``reason`` comes before ``path``."""

    reason: str
    path: str


class PlaintextVerdict(BaseModel):
    """The judge's structured answer: one decision for every numbered text, and any
    further paths from the tree it flags."""

    verdicts: list[TextVerdict]
    tree_findings: list[TreeFinding] = []


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


class JudgeTools:
    """The two tools of one judge call: a shell on ``container``, the judge's own copy of the
    server, a sandbox over ``snapshot``, and the calls made."""

    def __init__(
        self, container: ServerContainer, snapshot: ServerSnapshot, output_char_limit: int
    ) -> None:
        self._container = container
        self._inputs = server_dump(snapshot=snapshot)
        self._limits = SandboxLimits(
            wall_seconds=PYTHON_WALL_SECONDS,
            cpu_seconds=PYTHON_CPU_SECONDS,
            memory_bytes=PYTHON_MEMORY_BYTES,
            file_bytes=PYTHON_FILE_BYTES,
            output_bytes=output_char_limit,
        )
        self._output_char_limit = output_char_limit
        self.calls: list[JudgeToolCall] = []

    async def run_command(self, command: str) -> str:
        """Run ``command`` as root in the container and remember the call."""
        result = await self._container.exec_as_root(
            command=command, timeout_s=JUDGE_COMMAND_SECONDS, output_bytes=self._output_char_limit
        )
        output = format_output(output=result, char_limit=self._output_char_limit)
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


def server_dump(snapshot: ServerSnapshot) -> dict[str, str]:
    """The sandbox's inputs: every player file under ``SERVER_DUMP_DIR``, and the manifest."""
    inputs: dict[str, str] = {}
    manifest: list[dict[str, str]] = []
    for path, node in snapshot.player_nodes():
        manifest.append(
            {
                "path": path,
                "kind": node.kind.value,
                "owner": node.owner,
                "mode": f"{node.mode & MODE_MASK:04o}",
            }
        )
        if node.kind is NodeKind.FILE:
            inputs[f"{SERVER_DUMP_DIR}{path}"] = node.content
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
        output=ExecOutput(
            stdout=result.stdout,
            stderr=stderr,
            exit_status=result.exit_status,
            timed_out=result.timed_out,
        ),
        char_limit=char_limit,
    )


async def find_plaintext(
    config: PlaintextJudgeConfig,
    renderer: TemplateRenderer,
    container: ServerContainer,
    snapshot: ServerSnapshot,
    texts: list[WrittenText],
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
        container=container, snapshot=snapshot, output_char_limit=config.output_char_limit
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
            template_name=JUDGE_TEXTS_TEMPLATE,
            template_variables={"texts": texts, "tree": snapshot.tree_lines()},
        ),
        usage_limits=UsageLimits(request_limit=config.turn_limit),
    )
    reading = _read_verdict(
        verdict=result.output, texts=texts, snapshot=snapshot, tool_calls=tools.calls
    )
    logger.info(
        "Plaintext judge flagged %d of %d texts after %d tool calls",
        len(reading.findings),
        len(texts),
        len(tools.calls),
    )
    return reading


def _read_verdict(
    verdict: PlaintextVerdict,
    texts: list[WrittenText],
    snapshot: ServerSnapshot,
    tool_calls: list[JudgeToolCall],
) -> PlaintextReading:
    """Match the verdict's numbered decisions to ``texts``, and its tree findings to the
    snapshot's nodes. A tree finding naming no player node, or a text already flagged,
    is logged and dropped; one naming a numbered name the judge passed flags it instead."""
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
    owners = {path: node.owner for path, node in snapshot.player_nodes()}
    flagged = {finding.written.path for finding in findings}
    for tree_finding in verdict.tree_findings:
        if tree_finding.path not in owners or tree_finding.path in flagged:
            logger.warning(
                "Plaintext judge flagged %s from the tree, which is no player node or is "
                "already flagged; dropped",
                tree_finding.path,
            )
            continue
        flagged.add(tree_finding.path)
        findings.append(
            PlaintextFinding(
                written=name_text(path=tree_finding.path, author=owners[tree_finding.path]),
                reason=tree_finding.reason,
            )
        )
        passed = [
            text
            for text in passed
            if not (text.kind is WrittenTextKind.NAME and text.path == tree_finding.path)
        ]
    return PlaintextReading(findings=findings, passed=passed, tool_calls=tool_calls)
