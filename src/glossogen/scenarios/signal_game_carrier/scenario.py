"""Two players who must pick squares of the same colour, with a radio as their only link.

Each round both players read one song and put an executor in place: Python source whose
``noise(song)`` the world adds to the song, clipped. When both have called transmit the
recording is fixed, every player's noise and channel noise included, and each player
picks a square on its own private grid with end_round. There is no channel and no tool
that carries text to the partner.

The draws are in ``round_material``, executor runs in ``executor_run``, the round
state in ``world``. This module wires them to the platform.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Literal, NamedTuple

from glossogen.code_sandbox.python_runner import PythonRunResult, run_python
from glossogen.model_catalog import Provider
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.models.event_base import EventBase
from glossogen.models.runner_prompts import RunnerPrompts
from glossogen.runtime.activity_notification import DoneNotification, NewInfoNotification
from glossogen.runtime.notification_payload import Wake
from glossogen.runtime.scenario_tool import ScenarioTool
from glossogen.runtime.wait_for import WaitFor
from glossogen.runtime.wait_registry import WakeReason
from glossogen.scenario_base import PrimaryChannel, RoundResult
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenario_run_detail_extension import ScenarioRunDetailExtension
from glossogen.scenarios.signal_game_carrier.boards import Square, off_grid
from glossogen.scenarios.signal_game_carrier.events import (
    SignalGameCarrierExecutorRan,
    SignalGameCarrierRecordingReady,
    SignalGameCarrierRoundResolved,
    SignalGameCarrierRoundStarted,
    SignalGameCarrierSquareChosen,
    SignalGameCarrierTransmitted,
)
from glossogen.scenarios.signal_game_carrier.executor_run import (
    SANDBOX_LIMITS,
    exit_description,
    run_executor,
)
from glossogen.scenarios.signal_game_carrier.ids import (
    AGENT_IDS,
    AWAITING_YOU,
    BOARD_TEMPLATE,
    BOTH_CHOSE_TRIGGER,
    DESCRIPTION_TEMPLATE,
    END_ROUND_TOOL,
    EXECUTOR_RESULT_TEMPLATE,
    EXECUTOR_SOURCE_TEMPLATE,
    HIDDEN_BASE_TOOLS,
    INJECTION_TEMPLATE,
    PARTNER_OF,
    PROTOCOL_CONTINUE_TEMPLATE,
    PROTOCOL_INITIAL_TEMPLATE,
    PROTOCOL_SUFFIX_TEMPLATES,
    PYTHON_RESULT_TEMPLATE,
    READ_EXECUTOR_TOOL,
    READ_OUTPUT_TOOL,
    READ_RECORDING_TOOL,
    READ_SONG_TOOL,
    RECORDING_READY,
    RELEASE_NOTICE_TEMPLATE,
    RUN_PYTHON_TOOL,
    SEQUENCE_VIEW_TEMPLATE,
    SYSTEM_TEMPLATES,
    TOOL_NAMES,
    TRANSMIT_TOOL,
    TURN_NOTE_TEMPLATE,
    WRITE_EXECUTOR_TOOL,
    PromptDetail,
    SequenceKind,
    TurnNote,
)
from glossogen.scenarios.signal_game_carrier.knobs import SignalGameCarrierKnobs
from glossogen.scenarios.signal_game_carrier.round_material import generate_round_material
from glossogen.scenarios.signal_game_carrier.run_detail_extension import (
    SignalGameCarrierRunDetailExtension,
)
from glossogen.scenarios.signal_game_carrier.song import SongShape
from glossogen.scenarios.signal_game_carrier.tool_descriptions import tool_descriptions
from glossogen.scenarios.signal_game_carrier.wake_package import SignalGameCarrierWake
from glossogen.scenarios.signal_game_carrier.world import RoundOutcome, SignalGameCarrierWorld
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"

RELEASE_LIMIT = 2
"""Times per round a player is released from a wait by the parking hook. Past it the
player stays parked, and the round ends once both are."""

READ_NOTIFICATIONS_DESCRIPTION = (
    "read_notifications() returns your round briefing at startup and after a round changes; "
    "while you wait for your partner it returns once the recording is ready. "
    "read_notifications(wait_for='next_round') declares you are done with this round and "
    "waits for the next briefing. The result is a wake package: the reasons, any briefings, "
    "and a notice when the wait was cut short; type done ends the game. Must be the only "
    "tool call in its response."
)


class PreviousRound(NamedTuple):
    """The previous round as one player's briefing reads it: what each of the two picked,
    and whether the colours matched. A player that did not pick has no colour."""

    round_number: int
    your_colour: str | None
    partner_colour: str | None
    success: bool


class VisibleFile(NamedTuple):
    """One JSON file in a run_python working directory."""

    name: str
    values: list[int]


class SignalGameCarrierScenario(SimulationScenario):
    """The signal game played over a radio channel both players add noise to."""

    @classmethod
    def knobs_model(cls) -> type[SignalGameCarrierKnobs]:
        """Return the knobs model class for this scenario."""
        return SignalGameCarrierKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """The two players. The roster never varies with the knobs."""
        _ = knobs
        return [AgentRole(agent_id=agent_id, role_name=agent_id) for agent_id in AGENT_IDS]

    @classmethod
    def run_detail_extension(cls) -> ScenarioRunDetailExtension:
        """Each round's grids, song, noise and recording, which the run page draws."""
        return SignalGameCarrierRunDetailExtension()

    def __init__(self, knobs: SignalGameCarrierKnobs) -> None:
        self._knobs = knobs
        self._lean = knobs.prompt_detail is PromptDetail.LEAN
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = SignalGameCarrierWorld()
        self._material = generate_round_material(
            seed=knobs.seed,
            round_count=knobs.round_count,
            shape=SongShape(
                length=knobs.song_length,
                motif_length=knobs.motif_length,
                amplitude=knobs.song_amplitude,
            ),
            channel_noise_sigma=knobs.channel_noise_sigma,
            grid_size=knobs.grid_size,
            colour_count=knobs.colour_count,
        )
        self._lock = asyncio.Lock()
        # The round each player's current model request was issued in, so a call it
        # makes after that round ended is refused.
        self._request_round: dict[str, int] = {}
        # The last round whose briefing each player has received.
        self._briefed_round: dict[str, int] = {}
        self._started_round = 0

    def get_knobs(self) -> SignalGameCarrierKnobs:
        """Return this scenario's validated knobs instance."""
        return self._knobs

    def get_world(self) -> SignalGameCarrierWorld:
        """Return the round state: executors, transmissions, recording, picks, verdicts."""
        return self._world

    def scenario_description(self) -> str:
        """Describe the configured condition."""
        return self._renderer.render(template_name=DESCRIPTION_TEMPLATE, template_variables={})

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """One agent per player, in no channel, offered every scenario tool."""
        return [
            AgentConfig(
                agent_id=agent_id,
                role_name=agent_id,
                system_prompt=self._system_prompt(agent_id=agent_id),
                channel_ids=[],
                tool_names=list(TOOL_NAMES),
                model=default_model,
                provider=Provider(default_provider),
                compaction=self._knobs.compaction,
            )
            for agent_id in AGENT_IDS
        ]

    def _system_prompt(self, agent_id: str) -> str:
        """The rules, the same for both players but for the name they are given."""
        sigma = self._knobs.channel_noise_sigma
        return self._renderer.render(
            template_name=SYSTEM_TEMPLATES[self._knobs.prompt_detail],
            template_variables={
                "agent_id": agent_id,
                "grid_size": self._knobs.grid_size,
                "colour_count": self._knobs.colour_count,
                "song_length": self._knobs.song_length,
                "max_volume": self._knobs.max_volume,
                "channel_noise_sigma": sigma,
                "noise_spread": max(1, round(2 * sigma)),
                "round_count": self._knobs.round_count,
                "round_seconds": f"{self._knobs.max_round_duration_seconds:g}",
            },
        )

    def get_channels(self) -> list[Channel]:
        """None: the noise is the only thing that passes between the players."""
        return []

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """None, so the primary-channel metrics skip a run with no text."""
        return []

    def hidden_base_tools(self, agent_id: str) -> frozenset[str]:
        """Every base tool but ``read_notifications``."""
        _ = agent_id
        return HIDDEN_BASE_TOOLS

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Refuse every message: the run has no channel."""
        _ = agent_id, channel_id
        return "There is no messaging system."

    def runner_prompts(self, agent_id: str) -> RunnerPrompts | None:
        """The tool protocol, with no mention of messages."""
        _ = agent_id
        return RunnerPrompts(
            system_suffix=self._renderer.render(
                template_name=PROTOCOL_SUFFIX_TEMPLATES[self._knobs.prompt_detail],
                template_variables={},
            ),
            initial=self._renderer.render(
                template_name=PROTOCOL_INITIAL_TEMPLATE, template_variables={}
            ),
            continuation=self._renderer.render(
                template_name=PROTOCOL_CONTINUE_TEMPLATE, template_variables={}
            ),
        )

    def read_notifications_description(self) -> str:
        """Describe the wake package and the waits a player uses."""
        return READ_NOTIFICATIONS_DESCRIPTION

    def default_any_wait_timeout_s(self) -> float | None:
        """A plain wait ends only when something arrives: only the players change the round."""
        return None

    def ends_round_when_all_agents_waiting(self) -> bool:
        """Two parked players cannot change anything, so the round ends."""
        return True

    async def read_notifications(self, agent_id: str, wake: Wake) -> str:
        """Render a wake: briefings, and the notice when the scenario released the wait."""
        lifecycle = wake.inbox.take_lifecycle()
        briefings = [
            notification.text
            for notification in lifecycle
            if isinstance(notification, NewInfoNotification) and notification.kind == "injection"
        ]
        current = self.runtime.current_round
        if briefings:
            self._briefed_round[agent_id] = current
        notice: str | None = None
        if WakeReason.RELEASED in wake.reasons:
            notice = self._renderer.render(
                template_name=RELEASE_NOTICE_TEMPLATE,
                template_variables={"kind": wake.release_detail},
            )
        wake_type: Literal["wake", "done"] = "wake"
        if wake.terminated or any(
            isinstance(notification, DoneNotification) for notification in lifecycle
        ):
            wake_type = "done"
        return SignalGameCarrierWake(
            type=wake_type,
            round=current,
            wake_reasons=[reason.value for reason in wake.reasons],
            briefings=briefings,
            notice=notice,
        ).model_dump_json()

    def on_agent_parked(self, agent_id: str) -> None:
        """Resume a waiting player when the wait is over, or when nothing can end it.

        A player waiting after the recording is ready resumes to read it. A player that
        has not transmitted is told nothing will arrive until it does. Each player is
        released at most ``RELEASE_LIMIT`` times a round by this hook; past that it stays
        parked, and the round ends once both are. A player waiting for the next round is
        left parked.
        """
        if not self._world.round_open:
            return
        if self._briefed_round.get(agent_id) != self.runtime.current_round:
            return
        wait = self.runtime.parked_waits().get(agent_id)
        if wait is None or wait.wait_for is WaitFor.NEXT_ROUND:
            return
        detail = self._release_detail_for(agent_id=agent_id)
        if detail is None:
            return
        if not self._world.claim_release(agent_id=agent_id, limit=RELEASE_LIMIT):
            return
        self.runtime.release_wait(agent_id=agent_id, detail=detail)

    def _release_detail_for(self, agent_id: str) -> str | None:
        """Why a parked ``agent_id`` should resume now, or None when it should keep waiting."""
        if self._world.recording is not None:
            if self._world.square_of(agent_id=agent_id) is None:
                return RECORDING_READY
            return None
        if not self._world.has_transmitted(agent_id=agent_id):
            return AWAITING_YOU
        return None

    def on_model_request_started(self, agent_id: str) -> None:
        """Remember the round this model request was issued in."""
        self._request_round[agent_id] = self.runtime.current_round

    def get_injection(self, round_number: int, agent_id: str) -> str:
        """The round briefing: the previous round's two colours, and this round's grid."""
        material = self._material[round_number - 1]
        previous: PreviousRound | None = None
        outcome = self._world.outcome(round_number=round_number - 1)
        if outcome is not None:
            previous = PreviousRound(
                round_number=outcome.round_number,
                your_colour=outcome.colours.get(agent_id),
                partner_colour=outcome.colours.get(PARTNER_OF[agent_id]),
                success=outcome.success,
            )
        return self._renderer.render(
            template_name=INJECTION_TEMPLATE,
            template_variables={
                "round_number": round_number,
                "previous": previous,
                "board": self._board_view(grid=material.grids[agent_id]),
                "lean": self._lean,
                "has_executor": self._world.executor_of(agent_id=agent_id) is not None,
                "executor_failure": self._executor_failure_in(
                    round_number=round_number, agent_id=agent_id
                ),
            },
        )

    def _board_view(self, grid: list[list[str]]) -> str:
        """The player's own grid, as the briefing shows it."""
        return self._renderer.render(
            template_name=BOARD_TEMPLATE, template_variables={"grid": grid}
        )

    def _executor_failure_in(self, round_number: int, agent_id: str) -> str | None:
        """Why ``agent_id``'s executor in place failed on ``round_number``'s song, or None.

        None also when that round is not the open one, as when ``validate`` renders every
        round's briefing without playing the rounds.
        """
        if not self._world.round_open or self._world.material.round_number != round_number:
            return None
        return self._world.executor_failure_of(agent_id=agent_id)

    async def on_round_advanced(self, round_number: int) -> None:
        """Open the round, log its material, and play both executors in place on it."""
        if round_number <= self._started_round:
            return
        material = self._material[round_number - 1]
        self._world.start_round(material=material)
        self._started_round = round_number
        await self._log_event(
            event=SignalGameCarrierRoundStarted(
                round_number=round_number,
                grids=material.grids,
                song=material.song,
                channel_noise=material.channel_noise,
            )
        )
        async with self._lock:
            for agent_id in AGENT_IDS:
                await self._play_executor_in_place(round_number=round_number, agent_id=agent_id)

    def get_early_round_end_trigger(self) -> str | None:
        """End the round once both players have picked a square."""
        if self._world.round_open and self._world.both_chose:
            return BOTH_CHOSE_TRIGGER
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Resolve the round on the squares picked, if any."""
        async with self._lock:
            if self._world.outcome(round_number=round_number) is not None:
                return
            if not self._world.round_open:
                return
            outcome = self._world.resolve(round_number=round_number, trigger=trigger)
            await self._log_event(
                event=SignalGameCarrierRoundResolved(
                    round_number=round_number,
                    squares={
                        agent_id: [square.row, square.col]
                        for agent_id, square in outcome.squares.items()
                    },
                    colours=outcome.colours,
                    success=outcome.success,
                    trigger=trigger,
                )
            )

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Success when both squares hold the same colour. No judge."""
        _ = trigger
        outcome = self._world.outcome(round_number=round_number)
        if outcome is None:
            return []
        picked = ", ".join(
            f"{agent_id}={outcome.colours.get(agent_id, 'none')}" for agent_id in AGENT_IDS
        )
        return [RoundResult(success=outcome.success, team_id=None, reason=picked)]

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Seed resolved rounds and the executors in place, so a fork or resume carries on."""
        for event in events:
            if isinstance(event, SignalGameCarrierRoundResolved):
                self._world.seed_outcome(
                    outcome=RoundOutcome(
                        round_number=event.round_number,
                        squares={
                            agent_id: Square(row=pair[0], col=pair[1])
                            for agent_id, pair in event.squares.items()
                        },
                        colours=event.colours,
                        success=event.success,
                        trigger=event.trigger,
                    )
                )
                self._started_round = max(self._started_round, event.round_number)
            if isinstance(event, SignalGameCarrierExecutorRan) and event.written and event.accepted:
                self._world.place_executor(agent_id=event.agent_id, code=event.code)

    def get_tools(self) -> list[ScenarioTool]:
        """Every player has the same tools; each refuses a call made at the wrong moment."""
        descriptions = tool_descriptions(
            detail=self._knobs.prompt_detail,
            max_volume=self._knobs.max_volume,
            grid_size=self._knobs.grid_size,
        )
        return [
            ScenarioTool(
                name=READ_SONG_TOOL, description=descriptions.read_song, executor=self._read_song
            ),
            ScenarioTool(
                name=WRITE_EXECUTOR_TOOL,
                description=descriptions.write_executor,
                executor=self._write_executor,
            ),
            ScenarioTool(
                name=READ_OUTPUT_TOOL,
                description=descriptions.read_output,
                executor=self._read_output,
            ),
            ScenarioTool(
                name=TRANSMIT_TOOL, description=descriptions.transmit, executor=self._transmit
            ),
            ScenarioTool(
                name=READ_RECORDING_TOOL,
                description=descriptions.read_recording,
                executor=self._read_recording,
            ),
            ScenarioTool(
                name=END_ROUND_TOOL, description=descriptions.end_round, executor=self._end_round
            ),
            ScenarioTool(
                name=RUN_PYTHON_TOOL, description=descriptions.run_python, executor=self._run_python
            ),
            ScenarioTool(
                name=READ_EXECUTOR_TOOL,
                description=descriptions.read_executor,
                executor=self._read_executor,
            ),
        ]

    async def _read_song(self, agent_id: str) -> str:
        """This round's song, which both players play over."""
        round_number = self._open_round_for(agent_id=agent_id)
        return self._sequence_view(
            round_number=round_number,
            kind=SequenceKind.SONG,
            values=self._world.material.song,
        )

    async def _write_executor(self, agent_id: str, code: str) -> str:
        """Test ``code`` on the song and put it in place when it returns usable noise."""
        round_number = self._open_round_for(agent_id=agent_id)
        self._require_not_transmitted(agent_id=agent_id, tool_name=WRITE_EXECUTOR_TOOL)
        async with self._lock:
            run = await run_executor(
                code=code, song=self._world.material.song, max_volume=self._knobs.max_volume
            )
            if run.noise is not None:
                self._world.place_executor(agent_id=agent_id, code=code)
                self._world.set_noise(agent_id=agent_id, noise=run.noise)
                self._world.clear_executor_failure(agent_id=agent_id)
            await self._log_event(
                event=SignalGameCarrierExecutorRan(
                    round_number=round_number,
                    agent_id=agent_id,
                    code=code,
                    written=True,
                    accepted=run.noise is not None,
                    noise=run.noise,
                    clipped_ticks=run.clipped_ticks,
                    error=run.error,
                )
            )
        return self._renderer.render(
            template_name=EXECUTOR_RESULT_TEMPLATE,
            template_variables={
                "error": run.error,
                "kept": self._world.executor_of(agent_id=agent_id) is not None,
                "silent": self._world.executor_failure_of(agent_id=agent_id) is not None,
                "noise": run.noise,
                "clipped_ticks": run.clipped_ticks,
                "max_volume": self._knobs.max_volume,
                "printed": run.printed,
                "lean": self._lean,
            },
        )

    async def _read_output(self, agent_id: str) -> str:
        """The song with the caller's own noise added, before the channel mixes anything in."""
        round_number = self._open_round_for(agent_id=agent_id)
        song = self._world.material.song
        noise = self._world.noise_of(agent_id=agent_id)
        return self._sequence_view(
            round_number=round_number,
            kind=SequenceKind.OUTPUT,
            values=[tone + added for tone, added in zip(song, noise, strict=True)],
        )

    async def _transmit(self, agent_id: str) -> str:
        """Fix the caller's noise; mix the recording once both players have transmitted."""
        round_number = self._open_round_for(agent_id=agent_id)
        self._require_not_transmitted(agent_id=agent_id, tool_name=TRANSMIT_TOOL)
        async with self._lock:
            recording = self._world.transmit(agent_id=agent_id)
            await self._log_event(
                event=SignalGameCarrierTransmitted(
                    round_number=round_number,
                    agent_id=agent_id,
                    noise=self._world.noise_of(agent_id=agent_id),
                )
            )
            if recording is not None:
                await self._log_event(
                    event=SignalGameCarrierRecordingReady(
                        round_number=round_number, recording=recording
                    )
                )
        self._wake_partner(agent_id=agent_id)
        return self._renderer.render(
            template_name=TURN_NOTE_TEMPLATE,
            template_variables={
                "note": TurnNote.TRANSMITTED.value,
                "ready": recording is not None,
            },
        )

    async def _read_recording(self, agent_id: str) -> str:
        """What the channel carried, once both players have transmitted."""
        round_number = self._open_round_for(agent_id=agent_id)
        recording = self._world.recording
        if recording is None:
            raise ValueError(
                "The recording is not ready: your partner has not transmitted. Wait with "
                "read_notifications()."
            )
        return self._sequence_view(
            round_number=round_number, kind=SequenceKind.RECORDING, values=recording
        )

    async def _end_round(self, agent_id: str, row: int, col: int) -> str:
        """Record the square the caller picks on its own grid."""
        self._open_round_for(agent_id=agent_id)
        round_number = self._world.material.round_number
        square = Square(row=row, col=col)
        if off_grid(square=square, grid_size=self._knobs.grid_size):
            raise ValueError(
                f"row and col must be between 1 and {self._knobs.grid_size}. Nothing was picked."
            )
        async with self._lock:
            colour = self._world.choose(agent_id=agent_id, square=square)
            await self._log_event(
                event=SignalGameCarrierSquareChosen(
                    round_number=round_number,
                    agent_id=agent_id,
                    row=row,
                    col=col,
                    colour=colour,
                )
            )
        return self._renderer.render(
            template_name=TURN_NOTE_TEMPLATE,
            template_variables={
                "note": TurnNote.CHOSE.value,
                "colour": colour,
                "row": row,
                "col": col,
            },
        )

    async def _read_executor(self, agent_id: str) -> str:
        """The caller's own executor in place."""
        self._open_round_for(agent_id=agent_id)
        return self._renderer.render(
            template_name=EXECUTOR_SOURCE_TEMPLATE,
            template_variables={"code": self._world.executor_of(agent_id=agent_id)},
        )

    async def _run_python(self, agent_id: str, code: str) -> str:
        """Run ``code`` with the numbers ``agent_id`` can see as JSON files."""
        self._open_round_for(agent_id=agent_id)
        result = await run_python(
            code=code,
            inputs={
                visible.name: json.dumps(visible.values).encode("utf-8")
                for visible in self._visible_files(agent_id=agent_id)
            },
            limits=SANDBOX_LIMITS,
        )
        return self._renderer.render(
            template_name=PYTHON_RESULT_TEMPLATE,
            template_variables={
                "stdout": result.stdout,
                "stderr": result.stderr,
                "timed_out": result.timed_out,
                "wall_seconds": f"{SANDBOX_LIMITS.wall_seconds:g}",
                "output_cut": result.output_cut,
                "output_bytes": SANDBOX_LIMITS.output_bytes,
                "ending": self._program_ending(result=result),
            },
        )

    def _program_ending(self, result: PythonRunResult) -> str | None:
        """How a run_python program ended when it failed for a reason other than the
        wall-clock deadline, which the result already reports."""
        if result.exit_status == 0 or result.timed_out:
            return None
        return exit_description(exit_status=result.exit_status)

    def _visible_files(self, agent_id: str) -> list[VisibleFile]:
        """The numbers ``agent_id`` may read this round, as run_python's input files."""
        material = self._world.material
        files = [
            VisibleFile(name="song.json", values=material.song),
            VisibleFile(name="my_noise.json", values=self._world.noise_of(agent_id=agent_id)),
        ]
        recording = self._world.recording
        if recording is not None:
            files.append(VisibleFile(name="recording.json", values=recording))
        return files

    async def _play_executor_in_place(self, round_number: int, agent_id: str) -> None:
        """Run ``agent_id``'s executor in place on the new song and set its noise.

        Runs as the round opens, before the briefings, so a player whose executor fails on
        the new song reads that in its briefing. The caller holds the lock. With no
        executor in place, or one that fails, that player's noise stays silence.
        """
        code = self._world.executor_of(agent_id=agent_id)
        if code is None:
            return
        run = await run_executor(
            code=code, song=self._world.material.song, max_volume=self._knobs.max_volume
        )
        await self._log_event(
            event=SignalGameCarrierExecutorRan(
                round_number=round_number,
                agent_id=agent_id,
                code=code,
                written=False,
                accepted=run.noise is not None,
                noise=run.noise,
                clipped_ticks=run.clipped_ticks,
                error=run.error,
            )
        )
        if run.noise is None:
            assert run.error is not None
            self._world.record_executor_failure(agent_id=agent_id, error=run.error)
            return
        self._world.set_noise(agent_id=agent_id, noise=run.noise)

    def _sequence_view(self, round_number: int, kind: SequenceKind, values: list[int]) -> str:
        return self._renderer.render(
            template_name=SEQUENCE_VIEW_TEMPLATE,
            template_variables={
                "round_number": round_number,
                "kind": kind.value,
                "values": values,
                "lean": self._lean,
            },
        )

    def _wake_partner(self, agent_id: str) -> None:
        """Resume the partner if what just happened ends its wait.

        The partner is waiting for the recording, which is now ready, or it has not
        transmitted and is the one holding the round up. A partner that is not parked
        reads the change on its next call.
        """
        partner = PARTNER_OF[agent_id]
        wait = self.runtime.parked_waits().get(partner)
        if wait is None or wait.wait_for is WaitFor.NEXT_ROUND:
            return
        detail = self._release_detail_for(agent_id=partner)
        if detail is None:
            return
        self.runtime.release_wait(agent_id=partner, detail=detail)

    def _require_not_transmitted(self, agent_id: str, tool_name: str) -> None:
        """Refuse ``tool_name`` once ``agent_id`` has fixed its noise for the round."""
        if self._world.has_transmitted(agent_id=agent_id):
            raise ValueError(
                f"You already transmitted this round, so {tool_name} is refused. Read the "
                "recording once your partner has transmitted, then call end_round(row, col)."
            )

    def _open_round_for(self, agent_id: str) -> int:
        """The round ``agent_id``'s call belongs to.

        Refuses a call from a round that ended, and one from a player that has not read the
        current round's briefing.
        """
        current = self.runtime.current_round
        if not self._world.round_open:
            raise ValueError(
                f"Round {current} has ended. Call read_notifications(wait_for='next_round')."
            )
        requested = self._request_round.get(agent_id, current)
        if requested != current:
            raise ValueError(
                f"Round {requested} has ended. Call read_notifications() for the round "
                f"{current} briefing."
            )
        if self._briefed_round.get(agent_id) != current:
            raise ValueError(
                f"Round {current} has started and you have not read its briefing. Call "
                "read_notifications() first."
            )
        return current

    async def _log_event(self, event: EventBase) -> None:
        await self.runtime.event_logger.log(event=event)
