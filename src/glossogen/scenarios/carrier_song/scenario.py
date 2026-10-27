"""Two players who take turns sending a secret code through noise added to a song.

Each round one player is the sender. It reads the round's song and puts an executor
in place: Python source whose ``noise(song)`` the world adds to the song, clipped.
When the sender calls end_round the recording is fixed, channel noise included, and
the receiver, which waited until then, decodes the secret from it. There is no
channel and no tool that carries text to the partner.

The draws are in ``round_material``, executor runs in ``executor_run``, the round
state in ``world``. This module wires them to the platform.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Literal, NamedTuple

from glossogen.code_sandbox.python_runner import run_python
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
from glossogen.scenarios.carrier_song.events import (
    CarrierSongDecodingSubmitted,
    CarrierSongExecutorRan,
    CarrierSongRoundResolved,
    CarrierSongRoundStarted,
    CarrierSongTransmitted,
)
from glossogen.scenarios.carrier_song.executor_run import SANDBOX_LIMITS, run_executor
from glossogen.scenarios.carrier_song.ids import (
    AGENT_IDS,
    DECODED_TRIGGER,
    DESCRIPTION_TEMPLATE,
    END_ROUND_TOOL,
    EXECUTOR_RESULT_TEMPLATE,
    HIDDEN_BASE_TOOLS,
    INJECTION_TEMPLATE,
    PROTOCOL_CONTINUE_TEMPLATE,
    PROTOCOL_INITIAL_TEMPLATE,
    PROTOCOL_SUFFIX_TEMPLATE,
    PYTHON_RESULT_TEMPLATE,
    READ_OUTPUT_TOOL,
    READ_RECEIVED_TOOL,
    READ_SONG_TOOL,
    RELEASE_NOTICE_TEMPLATE,
    RUN_PYTHON_TOOL,
    SENDER_IDLE,
    SEQUENCE_VIEW_TEMPLATE,
    SUBMIT_DECODING_TOOL,
    SYSTEM_TEMPLATE,
    TOOL_NAMES,
    TRANSMITTED,
    TURN_NOTE_TEMPLATE,
    WRITE_EXECUTOR_TOOL,
    Role,
    SequenceKind,
    TurnNote,
)
from glossogen.scenarios.carrier_song.knobs import CarrierSongKnobs
from glossogen.scenarios.carrier_song.round_material import SongShape, generate_round_material
from glossogen.scenarios.carrier_song.run_detail_extension import CarrierSongRunDetailExtension
from glossogen.scenarios.carrier_song.secret_code import (
    code_problem,
    example_code,
    normalize_code,
)
from glossogen.scenarios.carrier_song.wake_package import CarrierSongWake
from glossogen.scenarios.carrier_song.world import CarrierSongWorld, RoundOutcome
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"

RELEASE_LIMIT = 2
"""Times per round a player is released from a wait. Past it the player stays parked,
and the round ends once both are."""

READ_SONG_DESCRIPTION = "Sender only. Returns this round's song, one whole number per tick."
READ_OUTPUT_DESCRIPTION = (
    "Sender only, before end_round. Returns the song with your executor's noise added, "
    "before channel noise."
)
END_ROUND_DESCRIPTION = (
    "Sender only. Fixes your noise for this round and hands the recording to the receiver. "
    "Nothing you do afterwards changes it."
)
SUBMIT_DECODING_DESCRIPTION = (
    "Receiver only, once the sender has ended its turn, once per round. secret is your "
    "reading of the sender's secret code: capital letters A-Z and digits 0-9, as many as "
    "the code has. Lowercase is read as uppercase. A decoding that is not a code of the "
    "right length is refused and does not count as your decoding. An accepted one ends "
    "the round."
)
RUN_PYTHON_DESCRIPTION = (
    "Runs a Python program, standard library only, in a fresh interpreter. Its working "
    "directory holds the numbers you can see this round as JSON lists: song.json, "
    "received.json. Returns what the program printed. It changes nothing in the game."
)
READ_NOTIFICATIONS_DESCRIPTION = (
    "read_notifications() returns your round briefing at startup and after a round changes; "
    "as the receiver it waits until the sender ends its turn. "
    "read_notifications(wait_for='next_round') declares you are done with this round and "
    "waits for the next briefing. The result is a wake package: the reasons, any briefings, "
    "and a notice when the wait was cut short; type done ends the game. Must be the only "
    "tool call in its response."
)


class PreviousRound(NamedTuple):
    """The previous round, as the briefing reads it. It was lost, or the run would have
    stopped. The briefing says only whether a decoding was submitted: neither the code
    nor the decoding, either of which would carry text between the players."""

    round_number: int
    submitted: bool


class VisibleFile(NamedTuple):
    """One JSON file in a run_python working directory."""

    name: str
    values: list[int]


class CarrierSongScenario(SimulationScenario):
    """Turn-taking transmission of a secret through noise on a song, with no channel."""

    @classmethod
    def knobs_model(cls) -> type[CarrierSongKnobs]:
        """Return the knobs model class for this scenario."""
        return CarrierSongKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """The two players. The roster never varies with the knobs."""
        _ = knobs
        return [AgentRole(agent_id=agent_id, role_name=agent_id) for agent_id in AGENT_IDS]

    @classmethod
    def run_detail_extension(cls) -> ScenarioRunDetailExtension:
        """Each round's song, noise and recording, which the run page draws."""
        return CarrierSongRunDetailExtension()

    def __init__(self, knobs: CarrierSongKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = CarrierSongWorld()
        self._material = generate_round_material(
            seed=knobs.seed,
            round_count=knobs.round_count,
            shape=SongShape(
                length=knobs.song_length,
                motif_length=knobs.motif_length,
                amplitude=knobs.song_amplitude,
            ),
            code_length=knobs.code_length,
            channel_noise_sigma=knobs.channel_noise_sigma,
        )
        self._lock = asyncio.Lock()
        # The round each player's current model request was issued in, so a
        # call it makes after that round ended is refused.
        self._request_round: dict[str, int] = {}
        # The last round whose briefing each player has received.
        self._briefed_round: dict[str, int] = {}
        self._started_round = 0

    def get_knobs(self) -> CarrierSongKnobs:
        """Return this scenario's validated knobs instance."""
        return self._knobs

    def get_world(self) -> CarrierSongWorld:
        """Return the round state: executors, transmission, decoding, verdicts."""
        return self._world

    def scenario_description(self) -> str:
        """Describe the configured condition."""
        return self._renderer.render(
            template_name=DESCRIPTION_TEMPLATE,
            template_variables={"receiver_sees_song": self._knobs.receiver_sees_song},
        )

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
            template_name=SYSTEM_TEMPLATE,
            template_variables={
                "agent_id": agent_id,
                "song_length": self._knobs.song_length,
                "code_length": self._knobs.code_length,
                "example_code": example_code(length=self._knobs.code_length),
                "max_volume": self._knobs.max_volume,
                "channel_noise_sigma": sigma,
                "noise_spread": max(1, round(2 * sigma)),
                "receiver_sees_song": self._knobs.receiver_sees_song,
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
                template_name=PROTOCOL_SUFFIX_TEMPLATE,
                template_variables={"receiver_sees_song": self._knobs.receiver_sees_song},
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
        return CarrierSongWake(
            type=wake_type,
            round=current,
            wake_reasons=[reason.value for reason in wake.reasons],
            briefings=briefings,
            notice=notice,
        ).model_dump_json()

    def on_agent_parked(self, agent_id: str) -> None:
        """Resume a waiting player when the wait is over, or when nothing can end it.

        A receiver waiting before it decoded resumes once the recording is ready,
        straight away when it already is. A sender waiting before it ended its turn
        is told nothing will arrive. Each player is released at most ``RELEASE_LIMIT``
        times a round by this hook; past that it stays parked, and the round ends
        once both are. A player waiting for the next round is left parked.
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
        transmitted = self._world.transmission is not None
        if self._world.role_of(agent_id=agent_id) is Role.RECEIVER:
            if transmitted and self._world.decoded is None:
                return TRANSMITTED
            return None
        if transmitted:
            return None
        return SENDER_IDLE

    def on_model_request_started(self, agent_id: str) -> None:
        """Remember the round this model request was issued in."""
        self._request_round[agent_id] = self.runtime.current_round

    def get_injection(self, round_number: int, agent_id: str) -> str:
        """The round briefing: the previous round's result, this round's role and secret."""
        material = self._material[round_number - 1]
        previous: PreviousRound | None = None
        outcome = self._world.outcome(round_number=round_number - 1)
        if outcome is not None:
            previous = PreviousRound(
                round_number=outcome.round_number, submitted=outcome.decoded is not None
            )
        is_sender = material.sender_id == agent_id
        secret: str | None = None
        executor_failure: str | None = None
        if is_sender:
            secret = material.secret
            executor_failure = self._executor_failure_in(round_number=round_number)
        return self._renderer.render(
            template_name=INJECTION_TEMPLATE,
            template_variables={
                "round_number": round_number,
                "previous": previous,
                "is_sender": is_sender,
                "secret": secret,
                "has_executor": self._world.executor_of(agent_id=agent_id) is not None,
                "executor_failure": executor_failure,
            },
        )

    def _executor_failure_in(self, round_number: int) -> str | None:
        """Why the sender's executor in place failed on ``round_number``'s song, or None.

        None also when that round is not the open one, as when ``validate`` renders
        every round's briefing without playing the rounds.
        """
        if not self._world.round_open or self._world.material.round_number != round_number:
            return None
        return self._world.executor_failure

    async def on_round_advanced(self, round_number: int) -> None:
        """Open the round, log its material, and play the sender's executor in place on it."""
        if round_number <= self._started_round:
            return
        material = self._material[round_number - 1]
        self._world.start_round(material=material)
        self._started_round = round_number
        await self._log_event(
            event=CarrierSongRoundStarted(
                round_number=round_number,
                sender_id=material.sender_id,
                receiver_id=material.receiver_id,
                secret=material.secret,
                song=material.song,
                channel_noise=material.channel_noise,
            )
        )
        async with self._lock:
            await self._play_executor_in_place(round_number=round_number)

    def is_finished_early(self) -> bool:
        """Stop the run once a round has been decoded correctly.

        Reads resolved rounds only, so the round that scored has its end and its
        verdict logged before the game clock stops.
        """
        return self._world.rounds_won() > 0

    def get_early_round_end_trigger(self) -> str | None:
        """End the round once the receiver has submitted its decoding."""
        if self._world.round_open and self._world.decoded is not None:
            return DECODED_TRIGGER
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Resolve the round on the decoding submitted, if any."""
        async with self._lock:
            if self._world.outcome(round_number=round_number) is not None:
                return
            if not self._world.round_open:
                return
            outcome = self._world.resolve(round_number=round_number, trigger=trigger)
            await self._log_event(
                event=CarrierSongRoundResolved(
                    round_number=round_number,
                    sender_id=outcome.sender_id,
                    receiver_id=outcome.receiver_id,
                    secret=outcome.secret,
                    decoded=outcome.decoded,
                    success=outcome.success,
                    trigger=trigger,
                )
            )

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Success when the decoding equals the secret. No judge."""
        _ = trigger
        outcome = self._world.outcome(round_number=round_number)
        if outcome is None:
            return []
        return [
            RoundResult(
                success=outcome.success,
                team_id=None,
                reason=f"secret={outcome.secret}, decoded={outcome.decoded}",
            )
        ]

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Seed resolved rounds and the executors in place, so a fork or resume carries on."""
        for event in events:
            if isinstance(event, CarrierSongRoundResolved):
                self._world.seed_outcome(
                    outcome=RoundOutcome(
                        round_number=event.round_number,
                        sender_id=event.sender_id,
                        receiver_id=event.receiver_id,
                        secret=event.secret,
                        decoded=event.decoded,
                        success=event.success,
                        trigger=event.trigger,
                    )
                )
                self._started_round = max(self._started_round, event.round_number)
            if isinstance(event, CarrierSongExecutorRan) and event.written and event.accepted:
                self._world.place_executor(agent_id=event.agent_id, code=event.code)

    def get_tools(self) -> list[ScenarioTool]:
        """The sender's, the receiver's and run_python; each refuses a call from the wrong role."""
        max_volume = self._knobs.max_volume
        write_executor_description = (
            "Sender only, before end_round. code is a Python program, standard library only, "
            "defining noise(song): it takes the song as a list of whole numbers and returns a "
            f"list of the same length, each value then limited to ±{max_volume}. Puts the "
            "executor in place and returns the noise it plays on this round's song. If it "
            "fails, its error is returned and the executor already in place is kept. Your "
            "partner never sees your code or what it prints."
        )
        read_received_description = (
            "Receiver only, once the sender has ended its turn. Returns the recording: the "
            "song plus the sender's noise plus channel noise."
        )
        if self._knobs.receiver_sees_song:
            read_received_description += " Also returns the song under it."
        return [
            ScenarioTool(
                name=READ_SONG_TOOL, description=READ_SONG_DESCRIPTION, executor=self._read_song
            ),
            ScenarioTool(
                name=WRITE_EXECUTOR_TOOL,
                description=write_executor_description,
                executor=self._write_executor,
            ),
            ScenarioTool(
                name=READ_OUTPUT_TOOL,
                description=READ_OUTPUT_DESCRIPTION,
                executor=self._read_output,
            ),
            ScenarioTool(
                name=END_ROUND_TOOL, description=END_ROUND_DESCRIPTION, executor=self._end_round
            ),
            ScenarioTool(
                name=READ_RECEIVED_TOOL,
                description=read_received_description,
                executor=self._read_received,
            ),
            ScenarioTool(
                name=SUBMIT_DECODING_TOOL,
                description=SUBMIT_DECODING_DESCRIPTION,
                executor=self._submit_decoding,
            ),
            ScenarioTool(
                name=RUN_PYTHON_TOOL, description=RUN_PYTHON_DESCRIPTION, executor=self._run_python
            ),
        ]

    async def _read_song(self, agent_id: str) -> str:
        """This round's song, for the sender."""
        round_number = self._open_round_for(agent_id=agent_id)
        self._require_role(agent_id=agent_id, role=Role.SENDER, tool_name=READ_SONG_TOOL)
        return self._sequence_view(
            round_number=round_number,
            kind=SequenceKind.SONG,
            values=self._world.material.song,
        )

    async def _write_executor(self, agent_id: str, code: str) -> str:
        """Test ``code`` on the song and put it in place when it returns usable noise."""
        round_number = self._open_round_for(agent_id=agent_id)
        self._require_playing_sender(agent_id=agent_id, tool_name=WRITE_EXECUTOR_TOOL)
        async with self._lock:
            run = await run_executor(
                code=code, song=self._world.material.song, max_volume=self._knobs.max_volume
            )
            if run.noise is not None:
                self._world.place_executor(agent_id=agent_id, code=code)
                self._world.set_noise(noise=run.noise)
            await self._log_event(
                event=CarrierSongExecutorRan(
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
                "noise": run.noise,
                "clipped_ticks": run.clipped_ticks,
                "max_volume": self._knobs.max_volume,
                "printed": run.printed,
            },
        )

    async def _read_output(self, agent_id: str) -> str:
        """The song with the sender's noise added, before channel noise."""
        round_number = self._open_round_for(agent_id=agent_id)
        self._require_playing_sender(agent_id=agent_id, tool_name=READ_OUTPUT_TOOL)
        song = self._world.material.song
        return self._sequence_view(
            round_number=round_number,
            kind=SequenceKind.OUTPUT,
            values=[tone + added for tone, added in zip(song, self._world.noise, strict=True)],
        )

    async def _end_round(self, agent_id: str) -> str:
        """Fix the sender's noise, mix the recording and wake the receiver."""
        round_number = self._open_round_for(agent_id=agent_id)
        self._require_playing_sender(agent_id=agent_id, tool_name=END_ROUND_TOOL)
        async with self._lock:
            transmission = self._world.transmit()
            await self._log_event(
                event=CarrierSongTransmitted(
                    round_number=round_number,
                    sender_id=agent_id,
                    noise=transmission.noise,
                    recording=transmission.recording,
                )
            )
        self._wake_receiver()
        return self._renderer.render(
            template_name=TURN_NOTE_TEMPLATE,
            template_variables={"note": TurnNote.TRANSMITTED.value},
        )

    async def _read_received(self, agent_id: str) -> str:
        """The recording, and the song under it when the receiver may see it."""
        round_number = self._open_round_for(agent_id=agent_id)
        self._require_role(agent_id=agent_id, role=Role.RECEIVER, tool_name=READ_RECEIVED_TOOL)
        transmission = self._world.transmission
        if transmission is None:
            raise ValueError(
                "Nothing has been transmitted yet. Wait with read_notifications() until your "
                "partner ends its turn."
            )
        view = self._sequence_view(
            round_number=round_number,
            kind=SequenceKind.RECORDING,
            values=transmission.recording,
        )
        if not self._knobs.receiver_sees_song:
            return view
        song_view = self._sequence_view(
            round_number=round_number,
            kind=SequenceKind.SONG,
            values=self._world.material.song,
        )
        return f"{view}\n{song_view}"

    async def _submit_decoding(self, agent_id: str, secret: str) -> str:
        """Record the receiver's reading of the secret code; the round then ends.

        A reading that is not a code of the round's length is refused and not recorded.
        """
        round_number = self._open_round_for(agent_id=agent_id)
        self._require_role(agent_id=agent_id, role=Role.RECEIVER, tool_name=SUBMIT_DECODING_TOOL)
        decoded = normalize_code(text=secret)
        problem = code_problem(code=decoded, length=self._knobs.code_length)
        if problem is not None:
            raise ValueError(f"{problem} Nothing was submitted.")
        async with self._lock:
            self._world.decode(value=decoded)
            await self._log_event(
                event=CarrierSongDecodingSubmitted(
                    round_number=round_number, receiver_id=agent_id, decoded=decoded
                )
            )
        return self._renderer.render(
            template_name=TURN_NOTE_TEMPLATE,
            template_variables={"note": TurnNote.DECODED.value},
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
                "exit_status": result.exit_status,
            },
        )

    def _visible_files(self, agent_id: str) -> list[VisibleFile]:
        """The numbers ``agent_id`` may read this round, as run_python's input files."""
        material = self._world.material
        if self._world.role_of(agent_id=agent_id) is Role.SENDER:
            return [VisibleFile(name="song.json", values=material.song)]
        transmission = self._world.transmission
        if transmission is None:
            return []
        files = [VisibleFile(name="received.json", values=transmission.recording)]
        if self._knobs.receiver_sees_song:
            files.append(VisibleFile(name="song.json", values=material.song))
        return files

    async def _play_executor_in_place(self, round_number: int) -> None:
        """Run the sender's executor in place on the new song and set the round's noise.

        Runs as the round opens, before the briefings, so a sender whose executor
        fails on the new song reads that in its briefing. The caller holds the lock.
        With no executor in place, or one that fails, the round's noise stays silence.
        """
        sender = self._world.material.sender_id
        code = self._world.executor_of(agent_id=sender)
        if code is None:
            return
        run = await run_executor(
            code=code, song=self._world.material.song, max_volume=self._knobs.max_volume
        )
        await self._log_event(
            event=CarrierSongExecutorRan(
                round_number=round_number,
                agent_id=sender,
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
            self._world.record_executor_failure(error=run.error)
            return
        self._world.set_noise(noise=run.noise)

    def _sequence_view(self, round_number: int, kind: SequenceKind, values: list[int]) -> str:
        return self._renderer.render(
            template_name=SEQUENCE_VIEW_TEMPLATE,
            template_variables={"round_number": round_number, "kind": kind.value, "values": values},
        )

    def _wake_receiver(self) -> None:
        """Resume the receiver if it is waiting for the transmission.

        A receiver that is not parked reads the recording on its next call, and one
        that parks before then is resumed by ``on_agent_parked``.
        """
        receiver = self._world.material.receiver_id
        wait = self.runtime.parked_waits().get(receiver)
        if wait is not None and wait.wait_for is not WaitFor.NEXT_ROUND:
            self.runtime.release_wait(agent_id=receiver, detail=TRANSMITTED)

    def _require_role(self, agent_id: str, role: Role, tool_name: str) -> None:
        """Refuse ``tool_name`` from a player that does not have ``role`` this round."""
        if self._world.role_of(agent_id=agent_id) is not role:
            raise ValueError(
                f"You are not the {role.value} this round, and only the {role.value} can call "
                f"{tool_name}."
            )

    def _require_playing_sender(self, agent_id: str, tool_name: str) -> None:
        """Refuse ``tool_name`` unless ``agent_id`` is the sender and has not ended its turn."""
        self._require_role(agent_id=agent_id, role=Role.SENDER, tool_name=tool_name)
        if self._world.transmission is not None:
            raise ValueError(
                "You already ended your turn this round. Call "
                "read_notifications(wait_for='next_round')."
            )

    def _open_round_for(self, agent_id: str) -> int:
        """The round ``agent_id``'s call belongs to.

        Refuses a call from a round that ended, and one from a player that has not
        read the current round's briefing.
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
