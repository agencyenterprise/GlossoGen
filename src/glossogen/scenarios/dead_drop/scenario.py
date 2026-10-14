"""Two analysts on one in-memory server, each holding the codebook entries the other needs.

The agents drive the server through a bash shell (``run_command``) and lock their
answers with ``submit_answer``. By default they share no channel, so whatever
passes between them passes through the filesystem. The round ends as soon as both
have submitted, and succeeds when both answered every request correctly.

The filesystem is built in ``server_filesystem``, the shell in ``shell_session``,
the round state in ``world``. This module wires them to the platform.
"""

import asyncio
from pathlib import Path
from typing import Any, Literal, NamedTuple

from glossogen.evaluation.metrics.communication.round_view import CommunicationRoundView
from glossogen.model_catalog import Provider
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.models.event import InjectionDelivered, SimulationEvent, SimulationStarted
from glossogen.models.event_base import EventBase
from glossogen.models.mcp_responses import SendMessageResult
from glossogen.models.runner_prompts import RunnerPrompts
from glossogen.runtime.activity_notification import DoneNotification, NewInfoNotification
from glossogen.runtime.notification_payload import Wake
from glossogen.runtime.scenario_tool import ScenarioTool
from glossogen.runtime.wait_for import WaitFor
from glossogen.runtime.wait_registry import WakeReason
from glossogen.scenario_protocol import (
    PrimaryChannel,
    RoundResult,
    SendMessageExecutor,
    SimulationScenario,
)
from glossogen.scenarios.dead_drop.case_generation import (
    VALUE_DIGITS,
    AgentCase,
    RoundCase,
    generate_cases,
)
from glossogen.scenarios.dead_drop.evaluation.build_communication_rounds import (
    build_communication_rounds,
)
from glossogen.scenarios.dead_drop.evaluation.fs_channel_use_metric import FsChannelUseMetric
from glossogen.scenarios.dead_drop.events import (
    AgentCaseRecord,
    DeadDropAnswerSubmitted,
    DeadDropCaseStarted,
    DeadDropCommandRun,
    DeadDropFsChanged,
    DeadDropRoundResolved,
)
from glossogen.scenarios.dead_drop.ids import (
    AGENT_IDS,
    BOTH_SUBMITTED_TRIGGER,
    CASE_TEMPLATE,
    DESCRIPTION_TEMPLATE,
    HIDDEN_CHANNEL_TOOLS,
    HOSTNAME,
    INJECTION_TEMPLATE,
    LINK_CHANNEL_ID,
    PROTOCOL_CONTINUE_TEMPLATE,
    PROTOCOL_INITIAL_TEMPLATE,
    PROTOCOL_SUFFIX_TEMPLATE,
    RELEASE_NOTICE_TEMPLATE,
    RUN_COMMAND_TOOL,
    SEND_MESSAGE_TOOL,
    SUBMIT_ANSWER_TOOL,
    SYSTEM_TEMPLATE,
    CaseDelivery,
    ChannelMode,
    case_file_path,
    home_of,
)
from glossogen.scenarios.dead_drop.knobs import DeadDropKnobs
from glossogen.scenarios.dead_drop.server_filesystem import ServerFilesystem
from glossogen.scenarios.dead_drop.shell_session import ShellSession, WaitBudget, build_commands
from glossogen.scenarios.dead_drop.wake_package import DeadDropWake
from glossogen.scenarios.dead_drop.world import DeadDropWorld, RoundOutcome, Submission
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"

RUN_COMMAND_DESCRIPTION = (
    "Run one bash command line on the server as your user and return what it printed: "
    "stdout, then stderr, then the exit status when it is not zero. Pipes, redirection, "
    "heredocs and loops work. Each call counts against your commands for the round."
)
SUBMIT_ANSWER_DESCRIPTION = (
    "Lock your answer for this round: a mapping from each requested key to its value, as "
    "text or as a number. The keys must be exactly the round's requests. The first accepted "
    "submission is final."
)
SEND_MESSAGE_DESCRIPTION = "Send text to the shared channel."
READ_NOTIFICATIONS_DESCRIPTION = (
    "read_notifications() returns your round briefing; call it at startup and after a round "
    "changes. read_notifications(wait_for='next_round') declares you are done with this "
    "round and waits for the next briefing. The result lists the wake reasons, any briefings "
    "and a notice when the wait was cut short; type done ends the session. Call it by itself: "
    "in a response that also calls another tool, it does not wait and returns at once, asking "
    "you to call it again on its own."
)
CHAT_WAIT_DESCRIPTION = (
    " read_notifications(wait_for='message') waits until a message arrives on the shared "
    "channel, and the result also lists the messages."
)


class CodebookLine(NamedTuple):
    """One codebook entry as the case file template reads it."""

    key: str
    value: str


class PreviousRound(NamedTuple):
    """The previous round's result from one agent's side, as the briefing reads it."""

    round_number: int
    own_status: str


async def _wall_clock_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _case_from_event(event: DeadDropCaseStarted) -> RoundCase:
    """The case a round was played with, as its log recorded it."""
    return RoundCase(
        round_number=event.round_number,
        by_agent={
            agent_case.agent_id: AgentCase(
                codebook=dict(agent_case.codebook), requests=tuple(agent_case.requests)
            )
            for agent_case in event.cases
        },
    )


def _answer_text(value: str | int) -> str:
    """A submitted value as the codebook writes it.

    A number is padded with leading zeros to the codebook's digit count, since a
    JSON number cannot carry them: ``466`` is ``0466``. Text is taken as written,
    surrounding whitespace stripped.
    """
    if isinstance(value, int):
        return f"{value:0{VALUE_DIGITS}d}"
    return value.strip()


def _status(outcome: RoundOutcome, agent_id: str) -> str:
    if agent_id not in outcome.submitted:
        return "not submitted"
    if outcome.agent_correct[agent_id]:
        return "correct"
    return "incorrect"


class DeadDropScenario(SimulationScenario):
    """Two analysts who can only reach each other through a shared server's files."""

    @classmethod
    def knobs_model(cls) -> type[DeadDropKnobs]:
        """Return the knobs model class for this scenario."""
        return DeadDropKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """The two analysts. The roster never varies with the knobs."""
        _ = knobs
        return [AgentRole(agent_id=agent_id, role_name=agent_id) for agent_id in AGENT_IDS]

    @classmethod
    def get_available_metric_names(cls) -> list[str]:
        """Every generic metric, plus ``fs_channel_use``, which only reads dead_drop runs."""
        return sorted(set(super().get_available_metric_names()) | {FsChannelUseMetric.name})

    def __init__(self, knobs: DeadDropKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = DeadDropWorld()
        self._cases = self._draw_cases(recorded={})
        self._server = ServerFilesystem(
            fs_isolated=knobs.fs_isolated, log_event=self._log_event, rounds=self._world
        )
        self._shells = {
            agent_id: self._new_shell(agent_id=agent_id, knobs=knobs) for agent_id in AGENT_IDS
        }
        # The round each agent's current model request was issued in, so a call
        # it makes after that round ended is refused.
        self._request_round: dict[str, int] = {}
        # The last round whose briefing each agent has received.
        self._briefed_round: dict[str, int] = {}
        self._prepared_round = 0
        self._pending_replay: list[EventBase] = []

    def _draw_cases(self, recorded: dict[int, RoundCase]) -> list[RoundCase]:
        """Every round's case from the knobs, the ``recorded`` rounds kept as logged."""
        return generate_cases(
            seed=self._knobs.seed,
            round_count=self._knobs.round_count,
            codebook_entries=self._knobs.codebook_entries,
            queries_per_agent=self._knobs.queries_per_agent,
            recorded=recorded,
        )

    def _new_shell(self, agent_id: str, knobs: DeadDropKnobs) -> ShellSession:
        """``agent_id``'s shell on its view of the server, with its own wait budget."""
        view = self._server.view_for(agent_id=agent_id)
        wait_budget = WaitBudget(seconds_per_command=knobs.max_sleep_seconds)
        return ShellSession(
            view=view,
            commands=build_commands(
                view=view,
                server=self._server,
                wait_budget=wait_budget,
                inotifywait_enabled=knobs.inotifywait_enabled,
                sleeper=_wall_clock_sleep,
            ),
            wait_budget=wait_budget,
            output_char_limit=knobs.command_output_char_limit,
        )

    @property
    def _chat(self) -> bool:
        return self._knobs.channel_mode is ChannelMode.CHAT

    @property
    def _case_in_file(self) -> bool:
        return self._knobs.case_delivery is CaseDelivery.FILE

    def get_knobs(self) -> DeadDropKnobs:
        """Return this scenario's validated knobs instance."""
        return self._knobs

    def get_world(self) -> DeadDropWorld:
        """Return the round state: submissions, command counts, verdicts."""
        return self._world

    def scenario_description(self) -> str:
        """Describe the configured condition."""
        return self._renderer.render(
            template_name=DESCRIPTION_TEMPLATE,
            template_variables={
                "chat": self._chat,
                "fs_isolated": self._knobs.fs_isolated,
                "round_count": self._knobs.round_count,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """One agent per analyst, with the channel only under ``channel_mode=chat``."""
        channel_ids: list[str] = []
        tool_names = [RUN_COMMAND_TOOL, SUBMIT_ANSWER_TOOL]
        if self._chat:
            channel_ids = [LINK_CHANNEL_ID]
            tool_names.append(SEND_MESSAGE_TOOL)
        return [
            AgentConfig(
                agent_id=agent_id,
                role_name=agent_id,
                system_prompt=self._system_prompt(agent_id=agent_id),
                channel_ids=list(channel_ids),
                tool_names=list(tool_names),
                model=default_model,
                provider=Provider(default_provider),
                max_tokens=self._knobs.agent_max_tokens,
                compaction=self._knobs.compaction,
            )
            for agent_id in AGENT_IDS
        ]

    def _system_prompt(self, agent_id: str) -> str:
        return self._renderer.render(
            template_name=SYSTEM_TEMPLATE,
            template_variables={
                "agent_id": agent_id,
                "hostname": HOSTNAME,
                "home": home_of(agent_id=agent_id),
                "case_in_file": self._case_in_file,
                "commands_per_round": self._knobs.commands_per_round,
            },
        )

    def get_channels(self) -> list[Channel]:
        """The shared channel under ``channel_mode=chat``; none otherwise."""
        if not self._chat:
            return []
        return [Channel(channel_id=LINK_CHANNEL_ID, name="link", member_agent_ids=list(AGENT_IDS))]

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """The shared channel under ``channel_mode=chat``; none otherwise, so the
        primary-channel metrics skip a filesystem-only run."""
        if not self._chat:
            return []
        return [
            PrimaryChannel(channel_id=LINK_CHANNEL_ID, team_id=None, includes_direct_channels=False)
        ]

    def hidden_base_tools(self, agent_id: str) -> frozenset[str]:
        """Channel browsing is withheld; so is ``send_message`` with no channel."""
        _ = agent_id
        if self._chat:
            return HIDDEN_CHANNEL_TOOLS
        return HIDDEN_CHANNEL_TOOLS | {SEND_MESSAGE_TOOL}

    def send_message_executor(self) -> SendMessageExecutor:
        """``send_message(text)``: post to the shared channel."""
        return self.send_to_partner

    async def send_to_partner(self, agent_id: str, text: str) -> SendMessageResult:
        """Post ``text`` on the shared channel."""
        return await self.runtime.publish_message(
            agent_id=agent_id, channel_id=LINK_CHANNEL_ID, text=text, force=True
        )

    def send_message_description(self) -> str:
        """The ``send_message`` description agents read."""
        return SEND_MESSAGE_DESCRIPTION

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Refuse every message when the run has no channel."""
        _ = agent_id, channel_id
        if not self._chat:
            return "There is no messaging system."
        return None

    def runner_prompts(self, agent_id: str) -> RunnerPrompts | None:
        """The shell protocol, with no mention of channels unless the run has one."""
        _ = agent_id
        variables: dict[str, object] = {"chat": self._chat}
        return RunnerPrompts(
            system_suffix=self._renderer.render(
                template_name=PROTOCOL_SUFFIX_TEMPLATE, template_variables=variables
            ),
            initial=self._renderer.render(
                template_name=PROTOCOL_INITIAL_TEMPLATE, template_variables=variables
            ),
            continuation=self._renderer.render(
                template_name=PROTOCOL_CONTINUE_TEMPLATE, template_variables=variables
            ),
        )

    def read_notifications_description(self) -> str:
        """Describe the wake package and the waits this run offers."""
        if self._chat:
            return READ_NOTIFICATIONS_DESCRIPTION + CHAT_WAIT_DESCRIPTION
        return READ_NOTIFICATIONS_DESCRIPTION

    async def read_notifications(self, agent_id: str, wake: Wake) -> str:
        """Render a wake: briefings, any release notice, and under chat the messages received.

        Everything is taken before the first await, so a message arriving while
        this renders stays unread and goes with the next wake.
        """
        lifecycle = wake.inbox.take_lifecycle()
        messages: list[str] = []
        if self._chat:
            for unread in self.runtime.drain_unread_channel_messages(agent_id=agent_id):
                messages.extend(
                    f"{message.sender_agent_id}: {message.text}"
                    for message in unread.messages
                    if message.sender_agent_id != agent_id
                )
        briefings = [
            notification.text
            for notification in lifecycle
            if isinstance(notification, NewInfoNotification)
        ]
        if briefings:
            self._briefed_round[agent_id] = self.runtime.current_round
        notice: str | None = None
        if WakeReason.RELEASED in wake.reasons:
            notice = wake.release_detail
        wake_type: Literal["wake", "done"] = "wake"
        if wake.terminated or any(
            isinstance(notification, DoneNotification) for notification in lifecycle
        ):
            wake_type = "done"
        package = DeadDropWake(
            type=wake_type,
            round=self.runtime.current_round,
            wake_reasons=[reason.value for reason in wake.reasons],
            briefings=briefings,
            messages=messages,
            notice=notice,
        )
        if self._chat:
            return package.model_dump_json()
        return package.model_dump_json(exclude={"messages"})

    def on_agent_parked(self, agent_id: str) -> None:
        """Release an agent waiting mid-round before it has submitted.

        With no channel nothing arrives through ``read_notifications`` until the
        next briefing, and the clock reads a team that is all parked as idle and
        ends the round. A briefed agent that has not submitted and is not waiting
        for the next round is told so instead of being left to wait. Once the
        round is resolved, the next briefing is what wakes it.
        """
        if self._chat:
            return
        round_number = self.runtime.current_round
        if self._world.is_resolved(round_number=round_number):
            return
        if self._world.has_submitted(round_number=round_number, agent_id=agent_id):
            return
        if self._briefed_round.get(agent_id) != round_number:
            return
        wait = self.runtime.parked_waits().get(agent_id)
        if wait is None or wait.wait_for is WaitFor.NEXT_ROUND:
            return
        self.runtime.release_wait(
            agent_id=agent_id,
            detail=self._renderer.render(
                template_name=RELEASE_NOTICE_TEMPLATE,
                template_variables={"round_number": round_number},
            ),
        )

    def on_model_request_started(self, agent_id: str) -> None:
        """Remember the round this model request was issued in."""
        self._request_round[agent_id] = self.runtime.current_round

    def get_injection(self, round_number: int, agent_id: str) -> str:
        """The round briefing: the previous round's result, then the case or the path of
        its file."""
        previous: PreviousRound | None = None
        outcome = self._world.outcome(round_number=round_number - 1)
        if outcome is not None:
            previous = PreviousRound(
                round_number=outcome.round_number,
                own_status=_status(outcome=outcome, agent_id=agent_id),
            )
        case_path: str | None = None
        case_text: str | None = None
        if self._case_in_file:
            case_path = case_file_path(agent_id=agent_id, round_number=round_number)
        else:
            case_text = self.case_text(round_number=round_number, agent_id=agent_id)
        return self._renderer.render(
            template_name=INJECTION_TEMPLATE,
            template_variables={
                "round_number": round_number,
                "case_path": case_path,
                "case_text": case_text,
                "previous": previous,
            },
        )

    def case_text(self, round_number: int, agent_id: str) -> str:
        """``agent_id``'s case for the round, as its case file or its briefing holds it."""
        agent_case = self._cases[round_number - 1].by_agent[agent_id]
        return self._renderer.render(
            template_name=CASE_TEMPLATE,
            template_variables={
                "round_number": round_number,
                "codebook": [
                    CodebookLine(key=key, value=value) for key, value in agent_case.codebook.items()
                ],
                "requests": list(agent_case.requests),
            },
        )

    async def on_round_advanced(self, round_number: int) -> None:
        """Lay out the round: rebuild the server when it does not persist, write each case
        file under ``case_delivery=file``, and log the case.

        After a fork or resume the logged files are replayed first; a round the
        replay already laid out is left as it was.
        """
        if self._pending_replay:
            await self._replay(events=self._pending_replay)
            self._pending_replay = []
        if round_number <= self._prepared_round:
            return
        if self._prepared_round == 0 or not self._knobs.fs_persists_across_rounds:
            await self._reset_server()
        case = self._cases[round_number - 1]
        if self._case_in_file:
            await self._write_case_files(round_number=round_number)
        await self._log_event(
            event=DeadDropCaseStarted(
                round_number=round_number,
                cases=[
                    AgentCaseRecord(
                        agent_id=agent_id,
                        codebook=dict(case.by_agent[agent_id].codebook),
                        requests=list(case.by_agent[agent_id].requests),
                    )
                    for agent_id in AGENT_IDS
                ],
            )
        )
        self._prepared_round = round_number

    async def _reset_server(self) -> None:
        await self._server.reset()
        for shell in self._shells.values():
            shell.restart()

    async def _write_case_files(self, round_number: int) -> None:
        for agent_id in AGENT_IDS:
            await self._server.write_system_file(
                path=case_file_path(agent_id=agent_id, round_number=round_number),
                content=self.case_text(round_number=round_number, agent_id=agent_id),
            )

    def get_early_round_end_trigger(self) -> str | None:
        """End the round as soon as both answers are locked."""
        if self._world.both_submitted(round_number=self.runtime.current_round):
            return BOTH_SUBMITTED_TRIGGER
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Resolve the round, counting an agent that never submitted as wrong."""
        if self._world.is_resolved(round_number=round_number):
            return
        outcome = self._world.resolve(round_number=round_number, trigger=trigger)
        await self._log_event(
            event=DeadDropRoundResolved(
                round_number=round_number,
                agent_correct=dict(outcome.agent_correct),
                submitted=list(outcome.submitted),
                success=outcome.success,
                trigger=trigger,
            )
        )

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Success when both agents answered every request correctly."""
        _ = trigger
        outcome = self._world.outcome(round_number=round_number)
        if outcome is None:
            return []
        reason = ", ".join(
            f"{agent_id}={_status(outcome=outcome, agent_id=agent_id)}" for agent_id in AGENT_IDS
        )
        return [RoundResult(success=outcome.success, team_id=None, reason=reason)]

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Seed cases, answers, commands, verdicts and briefings now; replay the files later.

        A round already logged keeps the case it was played with, even when the
        knobs a fork passes would draw a different one, and the rounds after it
        are drawn again without its keys. A briefing delivered before the resume
        counts as received: the platform does not deliver it again, and the
        agent's restored history holds it. Replaying writes to the filesystem,
        which awaits, so it waits for ``on_round_advanced``, which the clock calls
        before any agent acts.

        A log recorded under another ``case_delivery`` is refused: its rounds were
        laid out with or without case files, and replaying them needs the same.
        """
        for event in events:
            if isinstance(event, SimulationStarted):
                self._require_recorded_case_delivery(scenario_config=event.scenario_config)
        self._cases = self._draw_cases(
            recorded={
                event.round_number: _case_from_event(event=event)
                for event in events
                if isinstance(event, DeadDropCaseStarted)
            }
        )
        for event in events:
            if isinstance(event, DeadDropCommandRun):
                self._world.use_command(round_number=event.round_number, agent_id=event.agent_id)
            elif isinstance(event, InjectionDelivered):
                self._briefed_round[event.agent_id] = max(
                    self._briefed_round.get(event.agent_id, 0), event.round_number
                )
            elif isinstance(event, DeadDropAnswerSubmitted):
                self._world.restore_submission(
                    round_number=event.round_number,
                    agent_id=event.agent_id,
                    submission=Submission(
                        answers=dict(event.answers),
                        correct_keys=tuple(event.correct_keys),
                        all_correct=event.all_correct,
                    ),
                )
            elif isinstance(event, DeadDropRoundResolved):
                self._world.restore_outcome(
                    outcome=RoundOutcome(
                        round_number=event.round_number,
                        agent_correct=dict(event.agent_correct),
                        submitted=tuple(event.submitted),
                        success=event.success,
                        trigger=event.trigger,
                    )
                )
        self._pending_replay = [
            event for event in events if isinstance(event, DeadDropCaseStarted | DeadDropFsChanged)
        ]

    def _require_recorded_case_delivery(self, scenario_config: dict[str, Any]) -> None:
        """Raise when a logged run's ``case_delivery`` differs from this one's."""
        recorded = scenario_config.get("case_delivery")
        if recorded != self._knobs.case_delivery.value:
            raise ValueError(
                f"case_delivery is {self._knobs.case_delivery.value}, but the log was "
                f"recorded with {recorded}. A fork or resume keeps the recorded case_delivery."
            )

    async def _replay(self, events: list[EventBase]) -> None:
        """Rebuild the server from logged case starts and changes, in log order."""
        for event in events:
            if isinstance(event, DeadDropCaseStarted):
                if self._prepared_round == 0 or not self._knobs.fs_persists_across_rounds:
                    await self._reset_server()
                if self._case_in_file:
                    await self._write_case_files(round_number=event.round_number)
                self._prepared_round = event.round_number
            elif isinstance(event, DeadDropFsChanged):
                await self._server.replay(event=event)

    def build_communication_rounds(
        self, events: list[SimulationEvent]
    ) -> list[CommunicationRoundView]:
        """Each round's shared-file writes and the files copied or moved into the partner's
        reach, and chat messages under chat, with the case."""
        return build_communication_rounds(events=events, fs_isolated=self._knobs.fs_isolated)

    def get_tools(self) -> list[ScenarioTool]:
        """``run_command`` and ``submit_answer``."""

        async def run_command(agent_id: str, command: str) -> str:
            round_number = self._open_round_for(agent_id=agent_id)
            used = self._world.use_command(round_number=round_number, agent_id=agent_id)
            if used > self._knobs.commands_per_round:
                raise ValueError(
                    f"You have used all {self._knobs.commands_per_round} commands for round "
                    f"{round_number}. You can still call submit_answer."
                )
            await self._log_event(
                event=DeadDropCommandRun(round_number=round_number, agent_id=agent_id)
            )
            return await self._shells[agent_id].run(command=command, round_number=round_number)

        async def submit_answer(agent_id: str, answers: dict[str, str | int]) -> str:
            round_number = self._open_round_for(agent_id=agent_id)
            expected = self._cases[round_number - 1].expected_answers(agent_id=agent_id)
            normalized = {
                key.strip().upper(): _answer_text(value=value) for key, value in answers.items()
            }
            if set(normalized) != set(expected):
                raise ValueError(
                    f"Answer exactly these keys: {', '.join(sorted(expected))}. Nothing was "
                    "recorded."
                )
            submission = self._world.record_submission(
                round_number=round_number, agent_id=agent_id, answers=normalized, expected=expected
            )
            await self._log_event(
                event=DeadDropAnswerSubmitted(
                    round_number=round_number,
                    agent_id=agent_id,
                    answers=dict(submission.answers),
                    correct_keys=list(submission.correct_keys),
                    all_correct=submission.all_correct,
                )
            )
            return (
                f"Answer recorded for round {round_number}. Call "
                "read_notifications(wait_for='next_round') when you are done with this round."
            )

        return [
            ScenarioTool(
                name=RUN_COMMAND_TOOL, description=RUN_COMMAND_DESCRIPTION, executor=run_command
            ),
            ScenarioTool(
                name=SUBMIT_ANSWER_TOOL,
                description=SUBMIT_ANSWER_DESCRIPTION,
                executor=submit_answer,
            ),
        ]

    def _open_round_for(self, agent_id: str) -> int:
        """The round ``agent_id``'s call belongs to.

        Refuses a call from a round that ended, and a call from an agent that has
        not received the current round's briefing: without that refusal an agent
        that missed the round change keeps working on the previous case.
        """
        current = self.runtime.current_round
        if self._world.is_resolved(round_number=current):
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
