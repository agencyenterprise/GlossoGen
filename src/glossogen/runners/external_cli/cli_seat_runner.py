"""``ExternalCliRunner``: runs one seat in an agent CLI that connects to the run over MCP.

The runner serves the seat's tools (:mod:`.tool_server`), then starts the CLI
as a subprocess for each cycle: the platform's initial prompt first, and its
continuation prompt whenever the CLI ends a turn before the run has ended for
the seat. A later cycle resumes the CLI's own session, so the conversation
carries across processes. The CLI's tool calls are logged by the tool server;
the turn's usage, read from the CLI's output when it exits, is logged as
``cli_turn_completed`` and priced into the seat's cost. No model response is
logged, since none passes through the platform.

A turn whose process exits non-zero, or whose output reports a failure, is
logged as ``agent_run_cycle_failed``; after ``MAX_CONSECUTIVE_TURN_FAILURES``
such turns in a row the seat stops. Before the cycle that follows a failed one
the runner pauses, longer with each failure in a row, through ``pause_after_failure``
so a test can pass a wait that returns at once. A seat whose run has ended
is given ``TERMINATION_GRACE_SECONDS`` to end its turn; after that its process
is terminated. Each turn's stdout and stderr are kept under the seat's state
directory, and the CLI's transcripts are copied to ``transcripts/`` beside it
when the seat ends.
"""

import asyncio
import logging
import os
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path

from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import AgentRunCycleFailed, CliTurnCompleted, HarnessSessionBound
from glossogen.runners.agent_cost_accumulator import AgentCostAccumulator
from glossogen.runners.agent_run_result import AgentRunResult
from glossogen.runners.agent_runner_base import AgentRunner
from glossogen.runners.communication_protocol import build_full_system_prompt, runner_prompts_for
from glossogen.runners.external_cli.cli_protocol import (
    NO_USAGE,
    AgentCli,
    CliSeat,
    CliTurn,
    CliTurnResult,
)
from glossogen.runners.external_cli.tool_server import AgentToolServer
from glossogen.runners.harness_names import HARNESS_STATE_DIR_NAME
from glossogen.runners.harness_protocol import RunnerBuildContext
from glossogen.runners.read_notifications_tool import RunTermination
from glossogen.runtime.simulation_state import SimulationRuntime

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_TURN_FAILURES = 3
FAILURE_PAUSE_BASE_SECONDS = 30.0
TERMINATION_GRACE_SECONDS = 60.0
STDERR_TAIL_CHARS = 2000
TURN_OUTPUT_DIR_NAME = "turns"
TRANSCRIPTS_DIR_NAME = "transcripts"
"""Under the seat's state directory: each turn's stdout and stderr, for inspection."""

FailurePause = Callable[[int], Awaitable[None]]
"""Waits before the cycle after a failed one, given how many failed in a row."""


def failure_pause_seconds(consecutive_failures: int) -> float:
    """How long to wait after ``consecutive_failures`` failed turns in a row."""
    return FAILURE_PAUSE_BASE_SECONDS * 2 ** (consecutive_failures - 1)


async def pause_after_failures(consecutive_failures: int) -> None:
    """Wait longer after each failure in a row."""
    await asyncio.sleep(failure_pause_seconds(consecutive_failures=consecutive_failures))


class SeatKeptFailing(RuntimeError):
    """A seat's turns failed too many times in a row."""


class ExternalCliRunner(AgentRunner):
    """Runs one seat in ``cli``, recorded under ``harness_name``."""

    def __init__(
        self,
        context: RunnerBuildContext,
        harness_name: str,
        cli: AgentCli,
        pause_after_failure: FailurePause,
    ) -> None:
        self._context = context
        self._harness_name = harness_name
        self._cli = cli
        self._pause_after_failure = pause_after_failure

    async def start(
        self,
        agent_config: AgentConfig,
        runtime: SimulationRuntime,
        cost_tracker: dict[str, float],
    ) -> AgentRunResult:
        """Serve the seat's tools and run the CLI until the run ends for the seat."""
        if agent_config.initial_message_history is not None:
            raise ValueError(
                f"{self._harness_name} starts every seat fresh and cannot take "
                f"the reconstructed history given for {agent_config.agent_id}"
            )
        seat = _SeatRun(
            context=self._context,
            harness_name=self._harness_name,
            cli=self._cli,
            pause_after_failure=self._pause_after_failure,
            agent_config=agent_config,
            runtime=runtime,
            cost=AgentCostAccumulator(
                agent_id=agent_config.agent_id,
                model=agent_config.model,
                provider=agent_config.provider,
                event_bus=self._context.event_bus,
                cost_tracker=cost_tracker,
            ),
        )
        return await seat.run()


class _SeatRun:
    """One seat's run: its tool server, its CLI session, and its totals."""

    def __init__(
        self,
        context: RunnerBuildContext,
        harness_name: str,
        cli: AgentCli,
        pause_after_failure: FailurePause,
        agent_config: AgentConfig,
        runtime: SimulationRuntime,
        cost: AgentCostAccumulator,
    ) -> None:
        self._context = context
        self._harness_name = harness_name
        self._cli = cli
        self._pause_after_failure = pause_after_failure
        self._config = agent_config
        self._runtime = runtime
        self._cost = cost
        self._termination = RunTermination()
        self._session_id: str | None = None
        prompts = runner_prompts_for(
            role_name=agent_config.role_name,
            replacement=runtime.scenario.runner_prompts(agent_id=agent_config.agent_id),
        )
        self._initial_prompt = prompts.initial
        self._continuation_prompt = prompts.continuation
        self._system_prompt = build_full_system_prompt(
            base_prompt=agent_config.system_prompt, prompts=prompts
        )

    @property
    def _agent_id(self) -> str:
        return self._config.agent_id

    async def run(self) -> AgentRunResult:
        """Cycle until the run ends for the seat or ``max_turns`` cycles have run."""
        logger.info(
            "Starting %s seat %s (%s) model=%s max_turns=%d",
            self._harness_name,
            self._agent_id,
            self._config.role_name,
            self._config.model,
            self._context.max_turns,
        )
        if self._config.compaction.enabled:
            logger.warning(
                "Agent %s enables compaction, which %s does not apply: the CLI compacts "
                "on its own schedule",
                self._agent_id,
                self._harness_name,
            )
        tools = AgentToolServer(
            runtime=self._runtime, agent_id=self._agent_id, termination=self._termination
        )
        turns = 0
        seat: CliSeat | None = None
        try:
            endpoint = await tools.start()
            seat = self._seat(tool_url=endpoint.url, tool_token=endpoint.token)
            self._cli.prepare(seat=seat)
            consecutive_failures = 0
            while turns < self._context.max_turns and not self._termination.is_set:
                turns += 1
                failed = await self._run_turn(seat=seat, cycle=turns)
                if not failed:
                    consecutive_failures = 0
                    continue
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_TURN_FAILURES:
                    raise SeatKeptFailing(
                        f"the {self._harness_name} seat {self._agent_id} failed "
                        f"{consecutive_failures} turns in a row"
                    )
                await self._pause_after_failure(consecutive_failures)
            if turns >= self._context.max_turns:
                logger.warning("Agent %s hit max_turns limit (%d)", self._agent_id, turns)
        finally:
            self._runtime.scenario.on_agent_retired(agent_id=self._agent_id)
            await tools.stop()
            if seat is not None:
                await asyncio.to_thread(
                    keep_transcripts, seat=seat, source_dir=self._cli.transcripts_dir(seat=seat)
                )
        logger.info(
            "Agent %s finished. Total turns: %d, total cost: $%.4f",
            self._agent_id,
            turns,
            self._cost.cumulative_cost_usd,
        )
        return AgentRunResult(
            agent_id=self._agent_id,
            total_cost_usd=self._cost.cumulative_cost_usd,
            total_turns=turns,
        )

    def _seat(self, tool_url: str, tool_token: str) -> CliSeat:
        seat_dir = (self._context.run_dir / "harness" / self._agent_id).resolve()
        state_dir = seat_dir / HARNESS_STATE_DIR_NAME
        workspace = state_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        return CliSeat(
            agent_id=self._agent_id,
            model=self._config.model,
            system_prompt=self._system_prompt,
            max_output_tokens=self._config.max_tokens,
            state_dir=state_dir,
            workspace=workspace,
            tool_url=tool_url,
            tool_token=tool_token,
        )

    def _next_turn(self) -> CliTurn:
        """The initial prompt until the CLI has reported a session, the continuation after."""
        if self._session_id is None:
            return CliTurn(prompt=self._initial_prompt, resume_session_id=None)
        return CliTurn(prompt=self._continuation_prompt, resume_session_id=self._session_id)

    async def _run_turn(self, seat: CliSeat, cycle: int) -> bool:
        """Run one CLI process to completion and log what it reported; True when it failed."""
        turn = self._next_turn()
        command = self._cli.command(seat=seat, turn=turn)
        logger.debug("Agent %s cycle %d runs %s", self._agent_id, cycle, command)
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=seat.workspace,
                env=dict(self._cli.environment(seat=seat)),
            )
        except OSError as exc:
            logger.exception("Agent %s could not start its CLI", self._agent_id)
            await self._log_cycle_failure(
                cycle=cycle, error_type=type(exc).__name__, message=str(exc)
            )
            return True
        stdout, stderr = await self._communicate(process=process)
        exit_code = process.returncode
        if exit_code is None:
            exit_code = -1
        _keep_turn_output(seat=seat, cycle=cycle, stdout=stdout, stderr=stderr)
        result = self._parse(stdout=stdout, exit_code=exit_code, stderr=stderr)
        await self._record_turn(result=result, exit_code=exit_code)
        if result.is_error or exit_code != 0:
            await self._log_cycle_failure(
                cycle=cycle, error_type="CliTurnFailed", message=result.error_text
            )
            return True
        return False

    async def _communicate(self, process: asyncio.subprocess.Process) -> tuple[str, str]:
        """Wait for the process; once the run has ended for the seat, give it a grace period."""
        communicate = asyncio.ensure_future(process.communicate())
        try:
            while True:
                done, _ = await asyncio.wait({communicate}, timeout=TERMINATION_GRACE_SECONDS)
                if done:
                    break
                if self._termination.is_set:
                    logger.warning(
                        "Agent %s's CLI did not end its turn within %.0fs of the run ending; "
                        "terminating it",
                        self._agent_id,
                        TERMINATION_GRACE_SECONDS,
                    )
                    process.terminate()
                    break
            stdout, stderr = await communicate
        except asyncio.CancelledError:
            communicate.cancel()
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        return stdout.decode(errors="replace"), stderr.decode(errors="replace")

    def _parse(self, stdout: str, exit_code: int, stderr: str) -> CliTurnResult:
        """The turn's result, or a failed one saying what went wrong when it is unreadable."""
        try:
            result = self._cli.parse_output(stdout=stdout)
        except ValueError as exc:
            logger.exception(
                "Agent %s's CLI wrote output the harness could not read", self._agent_id
            )
            return CliTurnResult(
                session_id=self._session_id,
                usage=NO_USAGE,
                reported_cost_usd=None,
                is_error=True,
                error_text=f"{exc}; exit code {exit_code}; stderr: {stderr[-STDERR_TAIL_CHARS:]}",
            )
        if exit_code != 0 and not result.is_error:
            return result._replace(
                is_error=True,
                error_text=f"exit code {exit_code}; stderr: {stderr[-STDERR_TAIL_CHARS:]}",
            )
        return result

    async def _record_turn(self, result: CliTurnResult, exit_code: int) -> None:
        """Log the turn, bind the session it reported, and price its usage."""
        if result.session_id is not None and result.session_id != self._session_id:
            self._session_id = result.session_id
            await self._runtime.event_logger.log(
                event=HarnessSessionBound(
                    agent_id=self._agent_id,
                    round_number=self._runtime.current_round,
                    harness=self._harness_name,
                    session_id=result.session_id,
                )
            )
        await self._runtime.event_logger.log(
            event=CliTurnCompleted(
                agent_id=self._agent_id,
                round_number=self._runtime.current_round,
                harness=self._harness_name,
                session_id=result.session_id,
                usage=result.usage,
                reported_cost_usd=result.reported_cost_usd,
                exit_code=exit_code,
                is_error=result.is_error or exit_code != 0,
                error_text=result.error_text,
            )
        )
        self._cost.add_usage(
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            cache_read_tokens=result.usage.cache_read_input_tokens,
            cache_write_tokens=result.usage.cache_creation_input_tokens,
        )

    async def _log_cycle_failure(self, cycle: int, error_type: str, message: str) -> None:
        await self._runtime.event_logger.log(
            event=AgentRunCycleFailed(
                agent_id=self._agent_id,
                round_number=self._runtime.current_round,
                cycle=cycle,
                error_type=error_type,
                message=message,
            )
        )


def _keep_turn_output(seat: CliSeat, cycle: int, stdout: str, stderr: str) -> None:
    """Write what the turn's process printed under the seat's state directory."""
    turns = seat.state_dir / TURN_OUTPUT_DIR_NAME
    turns.mkdir(parents=True, exist_ok=True)
    (turns / f"turn-{cycle}.stdout").write_text(stdout)
    (turns / f"turn-{cycle}.stderr").write_text(stderr)


def keep_transcripts(seat: CliSeat, source_dir: Path) -> None:
    """Copy every ``*.jsonl`` under ``source_dir`` to the seat's ``transcripts/``, paths kept.

    The CLI's transcript is the seat's record of its conversation; the rest of
    its state directory is left out of archives and forks.
    """
    if not source_dir.is_dir():
        return
    kept = seat.state_dir.parent / TRANSCRIPTS_DIR_NAME
    for transcript in source_dir.rglob("*.jsonl"):
        destination = kept / transcript.relative_to(source_dir)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src=transcript, dst=destination)


def inherited_environment(removed_prefix: str, removed_names: frozenset[str]) -> dict[str, str]:
    """This process's environment less the variables a CLI must not inherit."""
    return {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(removed_prefix) and name not in removed_names
    }
