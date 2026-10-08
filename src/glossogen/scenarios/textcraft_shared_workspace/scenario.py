"""A team crafts every target of a layered recipe grid from one finite shared depot."""

import asyncio
import json
import random
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, NamedTuple

from glossogen.engine import team_structure
from glossogen.engine.team_declaration import RoleSpec
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import DIRECT_CHANNEL_PREFIX, Channel, ChannelTemplateEntry
from glossogen.models.message import SimulationMessage
from glossogen.models.runner_prompts import RunnerPrompts
from glossogen.runtime.activity_notification import (
    ActivityNotification,
    DoneNotification,
    NewInfoNotification,
)
from glossogen.runtime.notification_payload import Wake
from glossogen.runtime.scenario_tool import ScenarioTool
from glossogen.scenario_protocol import (
    PrimaryChannel,
    RoundResult,
    SendMessageExecutor,
    SimulationScenario,
)
from glossogen.scenarios.channel_noise import apply_character_noise
from glossogen.scenarios.textcraft_shared_workspace.events import (
    WorkspaceActionExecuted,
    WorkspaceCraftCompleted,
    WorkspaceMessageContextDelivered,
    WorkspaceRecipesDealt,
    WorkspaceRequestReleased,
    WorkspaceRoundResolved,
    WorkspaceTaskStarted,
)
from glossogen.scenarios.textcraft_shared_workspace.knobs import SharedWorkspaceKnobs
from glossogen.scenarios.textcraft_shared_workspace.recipe_dealing import deal_recipes
from glossogen.scenarios.textcraft_shared_workspace.state import (
    DepotState,
    PendingCraft,
    Transition,
)
from glossogen.scenarios.textcraft_shared_workspace.tasks import (
    WorkspaceTask,
    generate_task,
    load_task_manifest,
)
from glossogen.scenarios.textcraft_shared_workspace.tool_results import (
    LifecycleEntry,
    WorkspaceSendResult,
    WorkspaceWake,
)
from glossogen.scenarios.textcraft_shared_workspace.virtual_clock import (
    VirtualClock,
    VirtualClockConfig,
)
from glossogen.scenarios.textcraft_shared_workspace.world import (
    CHANNEL,
    TEAM,
    SharedWorkspaceWorld,
    seat_ids,
    seat_role_name,
    workspace_teams,
)
from glossogen.template_renderer import TemplateRenderer

DeliveryCarrier = Literal["act", "send", "observe", "wake"]

PUBLIC_MESSAGES_HEADER = "NEW PUBLIC MESSAGES"
NO_PUBLIC_MESSAGES = "none"
HIDDEN_CHANNEL_TOOLS = frozenset({"read_channel", "list_channels", "get_channel_members"})
"""Messages reach agents inside tool results, so the channel browsing tools are withheld."""


class PublicInboxDelivery(NamedTuple):
    """Message bodies and their rendered block for one tool response."""

    messages: list[SimulationMessage]
    rendered: str


class TextcraftSharedWorkspaceScenario(SimulationScenario):
    """Every agent sees every target; success requires all of them at once."""

    @classmethod
    def knobs_model(cls) -> type[SharedWorkspaceKnobs]:
        """Return the scenario's validated factors."""
        return SharedWorkspaceKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Resolve symmetric seats before a runtime exists.

        ``pool_agent_count`` wins, then ``crafter_count``; with neither, the
        single-agent baseline, one seat.
        """
        values: dict[str, Any] = {}
        if knobs is not None:
            values = knobs
        agent_count = 1
        if values.get("pool_agent_count") is not None:
            agent_count = int(values["pool_agent_count"])
        elif values.get("crafter_count") is not None:
            agent_count = int(values["crafter_count"])
        seats = seat_ids(agent_count=agent_count)
        return [AgentRole(agent_id=seat, role_name=seat_role_name(seat=seat)) for seat in seats]

    def __init__(self, knobs: SharedWorkspaceKnobs) -> None:
        self._knobs = knobs
        self.world = SharedWorkspaceWorld(knobs)
        self._teams = workspace_teams(seats=self.world.seats, comms_enabled=knobs.comms_enabled)
        self._renderer = TemplateRenderer(prompts_dirs=[Path(__file__).parent / "prompts"])
        self._noise_rng = random.Random(knobs.seed)
        self._lock = asyncio.Lock()
        # A crafter makes one timed craft at a time, even when it issues several.
        self._craft_locks = {seat: asyncio.Lock() for seat in self.world.seats}
        self._outcomes: dict[int, WorkspaceRoundResolved] = {}
        self._virtual_terminal_at: dict[int, float] = {}
        # The round each agent's current model request was issued in, so a
        # response released after that round ended is refused by ``act``.
        self._request_round: dict[str, int] = {}
        self._clock: VirtualClock | None = None
        if knobs.virtual_clock:
            self._clock = VirtualClock(
                config=VirtualClockConfig(
                    base_latency_s=knobs.virtual_base_latency_s,
                    output_tokens_per_second=knobs.virtual_output_tokens_per_second,
                ),
                agent_ids=list(self.world.seats),
            )
        self._tasks = self._load_tasks()

    def _load_tasks(self) -> list[WorkspaceTask]:
        """Read the task manifest, or generate the same tasks in every arm."""
        if self._knobs.task_manifest is not None:
            tasks = load_task_manifest(path=self._knobs.task_manifest)
            if len(tasks) < self._knobs.round_count:
                raise ValueError("manifest must contain at least round_count tasks")
            tasks = tasks[: self._knobs.round_count]
        else:
            tasks = [
                generate_task(
                    seed=self._knobs.seed + index,
                    width=self._knobs.crafter_count,
                    span=self._knobs.steps_per_agent,
                    quantity_scale=self._knobs.quantity_scale,
                    resource_slack_fraction=self._knobs.resource_slack_fraction,
                    max_fan_in=self._knobs.dag_max_fan_in,
                    cross_edge_density=self._knobs.dag_cross_edge_density,
                    raw_material_count=self._knobs.dag_raw_material_count,
                    max_raw_inputs=self._knobs.dag_max_raw_inputs,
                )
                for index in range(self._knobs.round_count)
            ]
        for task in tasks:
            if len(task.cards) != self._knobs.crafter_count:
                raise ValueError("every task must be crafter_count columns wide")
            task.certify()
        return tasks

    def get_knobs(self) -> SharedWorkspaceKnobs:
        """Return the active experiment configuration."""
        return self._knobs

    def get_world(self) -> SharedWorkspaceWorld:
        """Return the platform world."""
        return self.world

    def scenario_description(self) -> str:
        """Describe the experiment without disclosing any task."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "agent_count": self._knobs.agent_count,
                "crafter_count": self._knobs.crafter_count,
                "steps_per_agent": self._knobs.steps_per_agent,
                "recipe_holders": self._knobs.recipe_holders,
                "comms_enabled": self._knobs.comms_enabled,
            },
        )

    def _system(self, role: RoleSpec, channels: list[ChannelTemplateEntry]) -> str:
        """Render the shared rules; targets and recipes arrive in the round briefing."""
        return self._renderer.render(
            template_name=role.system_template,
            template_variables={
                "channels": channels,
                "comms_enabled": self._knobs.comms_enabled,
                "budget": self._knobs.round_time_budget_seconds,
                "agent_count": self._knobs.agent_count,
                "uncraft_enabled": self._knobs.uncraft_enabled,
                "craft_duration_s": self._knobs.craft_duration_s,
                "recipe_holders": self._knobs.recipe_holders,
                "agent_id": role.agent_id,
                "teammates": [seat for seat in self.world.seats if seat != role.agent_id],
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Build one agent per seat."""
        return team_structure.build_agent_configs(
            teams=self._teams,
            render_system_prompt=self._system,
            default_model=default_model,
            default_provider=default_provider,
            max_tokens=self._knobs.agent_max_tokens,
            compaction=self._knobs.compaction,
        )

    def on_model_request_started(self, agent_id: str) -> None:
        """Record the request's round and start its simulated latency at the current instant."""
        self._request_round[agent_id] = self.runtime.current_round
        if self._clock is not None:
            self._clock.begin_inference(agent_id=agent_id)

    async def gate_model_response(
        self, agent_id: str, input_tokens: int, output_tokens: int
    ) -> None:
        """Hold the response until its virtual turn, then charge it to the token pool."""
        if self._clock is not None:
            timing = await self._clock.complete_inference(
                agent_id=agent_id, output_tokens=output_tokens
            )
            await self.runtime.event_logger.log(
                event=WorkspaceRequestReleased(
                    round_number=self.runtime.current_round,
                    agent_id=agent_id,
                    started_at_s=timing.started_at,
                    completed_at_s=timing.completed_at,
                    output_tokens=output_tokens,
                )
            )
        if self._knobs.team_token_limit is None:
            return
        self.world.record_model_usage(tokens=input_tokens + output_tokens)
        self._note_virtual_terminal(round_number=self.runtime.current_round)

    def schedule_wait_timeout(
        self, agent_id: str, timeout_s: float, fire: Callable[[], None]
    ) -> Callable[[], None]:
        """Count a parked agent's timeout in virtual seconds when the clock runs."""
        if self._clock is None:
            return super().schedule_wait_timeout(agent_id=agent_id, timeout_s=timeout_s, fire=fire)
        return self._clock.schedule_timer(delay_seconds=timeout_s, callback=fire)

    def default_any_wait_timeout_s(self) -> float | None:
        """A plain wait ends only on a notification: nothing changes the depot but agents."""
        return None

    def clock_now_s(self) -> float:
        """Virtual seconds when the clock runs, so waits report virtual durations."""
        if self._clock is None:
            return super().clock_now_s()
        return self._clock.time()

    def on_agent_parked(self, agent_id: str) -> None:
        """A parked agent is not a lower bound on when anyone acts next."""
        if self._clock is not None:
            self._clock.park(agent_id=agent_id)

    def on_agent_resumed(self, agent_id: str) -> None:
        """A resumed agent's next request starts at the instant that woke it."""
        if self._clock is not None:
            self._clock.wake(agent_id=agent_id)

    def on_agent_retired(self, agent_id: str) -> None:
        """A runner that returned is no longer scheduled."""
        if self._clock is not None:
            self._clock.retire(agent_id=agent_id)

    def on_agent_enlisted(self, agent_id: str) -> None:
        """A swapped-in runner is scheduled from the swap instant on."""
        if self._clock is not None:
            self._clock.enlist(agent_id=agent_id)

    def on_simulation_stopping(self) -> None:
        """Release every response the clock still holds."""
        if self._clock is not None:
            self._clock.stop()

    def _note_virtual_terminal(self, round_number: int) -> None:
        """Remember the virtual instant this round first met a terminal condition."""
        clock = self._clock
        if clock is None or self.world.closed or round_number in self._virtual_terminal_at:
            return
        if self.world.terminal_trigger is not None:
            self._virtual_terminal_at[round_number] = clock.round_elapsed_s()

    def ends_round_when_all_agents_waiting(self) -> bool:
        """The depot changes only through agents' actions, so a fully parked team is final."""
        return True

    def get_channels(self) -> list[Channel]:
        """One public broadcast channel."""
        return team_structure.channels(teams=self._teams)

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """The broadcast channel, scored with the direct channels created in the run."""
        return [PrimaryChannel(channel_id=CHANNEL, team_id=None, includes_direct_channels=True)]

    def get_injection(self, round_number: int, agent_id: str) -> str:
        """The round briefing: every target, the agent's recipes and the depot."""
        task = self._tasks[round_number - 1]
        initial_depot = ", ".join(f"{i}={n}" for i, n in sorted(task.initial_depot.items()))
        targets = Counter(card.target for card in task.cards.values())
        recipes = sorted(recipe.command for recipe in task.recipes)
        recipe_total = len(recipes)
        holders = self._knobs.recipe_holders
        if holders is not None:
            recipes = self._recipe_hands(task=task, holders=holders)[agent_id]
        return self._renderer.render(
            template_name="crafter_injection.jinja",
            template_variables={
                "round_number": round_number,
                "agent_count": self._knobs.agent_count,
                "targets": [
                    _target_label(item=item, count=count) for item, count in sorted(targets.items())
                ],
                "recipes": recipes,
                "recipe_holders": holders,
                "recipe_total": recipe_total,
                "initial_depot": initial_depot,
                "actions": self.world.team_action_allowance(task=task),
            },
        )

    def _recipe_hands(self, task: WorkspaceTask, holders: int) -> dict[str, list[str]]:
        """Each agent's dealt recipes under ``recipe_holders``."""
        return deal_recipes(task=task, seats=self.world.seats, holders=holders)

    async def on_round_advanced(self, round_number: int) -> None:
        """Start the task, reset observer cursors, and log the task's ground truth."""
        async with self._lock:
            task = self._tasks[round_number - 1]
            self.world.start(task=task)
            clock = self._clock
            if clock is not None:
                clock.start_round()
            await self.runtime.event_logger.log(
                event=WorkspaceTaskStarted(
                    round_number=round_number,
                    task_id=task.task_id,
                    manifest=task.model_dump(),
                    comms_enabled=self._knobs.comms_enabled,
                )
            )
            holders = self._knobs.recipe_holders
            if holders is not None:
                await self.runtime.event_logger.log(
                    event=WorkspaceRecipesDealt(
                        round_number=round_number,
                        task_id=task.task_id,
                        holders=holders,
                        hands=self._recipe_hands(task=task, holders=holders),
                    )
                )

    def get_early_round_end_trigger(self) -> str | None:
        """Finish on collective completion or exhausted budgets."""
        return self.world.terminal_trigger

    def _result(self, round_number: int, trigger: str) -> WorkspaceRoundResolved:
        """Freeze one outcome; repeated judgement cannot change a finished round."""
        if round_number not in self._outcomes:
            state = self.world.state
            if state is None:
                raise RuntimeError("round has not started")
            self._outcomes[round_number] = WorkspaceRoundResolved(
                round_number=round_number,
                task_id=state.task.task_id,
                success=state.solved and not self.world.budget_exceeded,
                trigger=trigger,
                characters_used=self.world.characters_used(team_id=TEAM),
                actions_used=dict(self.world.actions),
                transitions=state.version,
                failed_crafts=state.failed_crafts,
                targets_satisfied=sum(
                    state.depot[c.target] >= 1 for c in state.task.cards.values()
                ),
                depot=dict(state.depot),
                virtual_elapsed_seconds=self._virtual_elapsed(round_number=round_number),
            )
        return self._outcomes[round_number]

    def _virtual_elapsed(self, round_number: int) -> float | None:
        """Virtual seconds to the terminal condition, else to now; None at wall-clock pace."""
        clock = self._clock
        if clock is None:
            return None
        return self._virtual_terminal_at.get(round_number, clock.round_elapsed_s())

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Close action and message admission and write the deterministic outcome."""
        async with self._lock:
            self.world.closed = True
            await self.runtime.event_logger.log(
                event=self._result(round_number=round_number, trigger=trigger)
            )

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """No LLM judge; targets coexist and speech stays within budget."""
        result = self._result(round_number=round_number, trigger=trigger)
        return [
            RoundResult(
                success=result.success,
                team_id=None,
                reason=(
                    f"{result.targets_satisfied}/{self._knobs.crafter_count} targets; "
                    f"{result.trigger}"
                ),
            )
        ]

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Accept the broadcast and direct channels, while messaging is on and the round open."""
        on_team_channel = channel_id == CHANNEL or channel_id.startswith(DIRECT_CHANNEL_PREFIX)
        if not on_team_channel or agent_id not in self.world.seats:
            return "Only the workspace broadcast and direct messages are available."
        if not self._knobs.comms_enabled:
            return "Broadcast is disabled in this condition."
        if self.world.closed or self.world.terminal_trigger is not None:
            return "Round closed."
        return None

    def transform_outgoing_message(self, agent_id: str, channel_id: str, text: str) -> str:
        """Use the platform's noise mechanism on the metered channels."""
        _ = agent_id
        if channel_id != CHANNEL and not channel_id.startswith(DIRECT_CHANNEL_PREFIX):
            return text
        return apply_character_noise(
            text=text,
            noise_level=self._knobs.channel_noise_level,
            mode=self._knobs.noise_replacement_mode,
            rng=self._noise_rng,
        )

    def _public_inbox(self, agent: str) -> PublicInboxDelivery:
        """Drain the agent's unread messages, on every channel it is in, for a tool result.

        The agent's own messages advance its read position but are never
        rendered back. An agent that cannot message is told nothing about messages.
        """
        if not self._knobs.comms_enabled:
            return PublicInboxDelivery(messages=[], rendered="")
        messages = [
            message
            for unread in self.runtime.drain_unread_channel_messages(agent_id=agent)
            for message in unread.messages
            if message.sender_agent_id != agent
        ]
        messages.sort(key=lambda message: message.timestamp)
        if not messages:
            return PublicInboxDelivery(
                messages=[], rendered=f"{PUBLIC_MESSAGES_HEADER}\n{NO_PUBLIC_MESSAGES}"
            )
        lines = [PUBLIC_MESSAGES_HEADER]
        for message in messages:
            audience = _audience(channel_id=message.channel_id, sender=message.sender_agent_id)
            lines.append(
                f"[round {message.round_number}; {message.sender_display_name}; "
                f"id={message.message_id}; to={audience}] {message.text}"
            )
        return PublicInboxDelivery(messages=messages, rendered="\n".join(lines))

    async def _log_inbox(
        self,
        agent: str,
        carrier: DeliveryCarrier,
        delivery: PublicInboxDelivery,
        round_number: int,
    ) -> None:
        """Record which message bodies one tool result carried into the agent's context."""
        message_ids_by_channel: dict[str, list[str]] = {}
        for message in delivery.messages:
            message_ids_by_channel.setdefault(message.channel_id, []).append(message.message_id)
        for channel_id in sorted(message_ids_by_channel):
            await self.runtime.event_logger.log(
                event=WorkspaceMessageContextDelivered(
                    round_number=round_number,
                    agent_id=agent,
                    channel_id=channel_id,
                    delivery_carrier=carrier,
                    message_ids=message_ids_by_channel[channel_id],
                )
            )

    @staticmethod
    def _with_inbox(observation: str, delivery: PublicInboxDelivery) -> str:
        """Append the rendered inbox block to an observation."""
        if not delivery.rendered:
            return observation
        return f"{observation}\n\n{delivery.rendered}"

    async def _deliver(self, agent: str, carrier: DeliveryCarrier, action_result: str) -> str:
        """The one delivery path for observations that are not workspace actions.

        Takes the world lock, renders the depot view (advancing the agent's
        observation cursor), drains the inbox (advancing its message cursor) and
        logs the delivery. ``send_message``, ``observe`` and wake-ups all go
        through here so a message is delivered exactly once whichever carried it.
        """
        async with self._lock:
            if carrier == "send":
                # A send can exhaust the character budget; note the instant.
                self._note_virtual_terminal(round_number=self.runtime.current_round)
            observation = self.world.observe(agent=agent, action_result=action_result)
            delivery = self._public_inbox(agent=agent)
            observation = self._with_inbox(observation=observation, delivery=delivery)
            await self._log_inbox(
                agent=agent,
                carrier=carrier,
                delivery=delivery,
                round_number=self.runtime.current_round,
            )
            return observation

    def send_message_executor(self) -> SendMessageExecutor:
        """``send_message(text, to)``: broadcast, or address named teammates."""
        return self.send_to_team

    def validate_direct_channel(self, agent_id: str, recipient_agent_ids: list[str]) -> str | None:
        """Every agent is on the one team, so any teammate may be addressed."""
        _ = agent_id, recipient_agent_ids
        return None

    def send_message_description(self) -> str:
        """Describe addressing and the receipt."""
        return (
            "Send text to the team. Omit 'to' to broadcast, or set 'to' to a list of "
            "teammate IDs to address only them. Charged to the shared character budget. Stored at "
            "once; nothing is held back because someone else spoke. Queued does not "
            "mean read or agreed. The receipt includes your current workspace "
            "observation and any messages you have not seen."
        )

    async def send_to_team(
        self, agent_id: str, text: str, to: list[str] | None = None
    ) -> WorkspaceSendResult:
        """Post ``text`` on the broadcast, or on the direct channel with ``to``.

        ``to`` defaults to None because the signature is the tool's schema, and a
        model broadcasts by leaving it out.
        """
        channel_id = CHANNEL
        rejection = self.validate_outgoing_message(agent_id=agent_id, channel_id=CHANNEL)
        if to is not None and rejection is None:
            channel_id = await self.runtime.direct_channel_for(
                agent_id=agent_id, recipient_agent_ids=to
            )
        published = await self.runtime.publish_message(
            agent_id=agent_id, channel_id=channel_id, text=text, force=True
        )
        workspace: str | None = None
        if published.status == "sent" and self.world.state is not None:
            workspace = await self._deliver(
                agent=agent_id, carrier="send", action_result="Message sent."
            )
        status: Literal["sent", "rejected"] = "rejected"
        if published.status == "sent":
            status = "sent"
        return WorkspaceSendResult(
            status=status,
            detail=published.detail,
            message_id=published.message_id,
            token_count=published.token_count,
            current_round=published.current_round,
            workspace=workspace,
        )

    async def read_notifications(self, agent_id: str, wake: Wake) -> str:
        """Render a wake: its reasons, the workspace, and the briefings it brought.

        The depot view, the message bodies and the briefings are taken in one
        step under the lock, before anything awaits, so a message that arrives
        while the wake is being logged stays unread and goes with the next
        result. The end of the run renders as ``done``, with the final workspace.
        """
        reasons = [reason.value for reason in wake.reasons]
        async with self._lock:
            workspace: str | None = None
            delivery = PublicInboxDelivery(messages=[], rendered="")
            if self.world.state is not None:
                observation = self.world.observe(
                    agent=agent_id, action_result=f"Woke: {', '.join(reasons)}."
                )
                delivery = self._public_inbox(agent=agent_id)
                workspace = self._with_inbox(observation=observation, delivery=delivery)
            lifecycle = [
                _lifecycle_entry(notification) for notification in wake.inbox.take_lifecycle()
            ]
            await self._log_inbox(
                agent=agent_id,
                carrier="wake",
                delivery=delivery,
                round_number=self.runtime.current_round,
            )
        entries = [entry for entry in lifecycle if entry is not None]
        wake_type: Literal["wake", "done"] = "wake"
        if wake.terminated:
            wake_type = "done"
            if not any(entry.type == "done" for entry in entries):
                entries.append(LifecycleEntry(type="done", text=None, reason=wake.done_reason))
        return json.dumps(
            WorkspaceWake(
                type=wake_type,
                wake_reasons=reasons,
                round=self.runtime.current_round,
                waited_seconds=wake.waited_seconds,
                workspace=workspace,
                lifecycle=entries,
            ).model_dump()
        )

    def read_notifications_description(self) -> str:
        """Describe the wake package this scenario returns, and only the waits it offers."""
        message_wait = ""
        messages = ""
        if self._knobs.comms_enabled:
            message_wait = (
                "wait_for='message' parks you until a teammate's message arrives, the next "
                "briefing arrives, or timeout_s passes. "
            )
            messages = ", every message that arrived"
        return (
            "Free. read_notifications() returns your task card at startup; otherwise it "
            f"waits until something arrives. {message_wait}wait_for='next_round' declares "
            "you finished with this round and parks you until the next briefing. The "
            f"result is a wake package: the reasons, the current workspace{messages}, and "
            "any briefing or end-of-run notice (type done ends the run). Must be the only "
            "tool call in its response."
        )

    def hidden_base_tools(self, agent_id: str) -> frozenset[str]:
        """Channel browsing is withheld, since messages arrive inside tool results; so is
        ``send_message`` when messaging is off."""
        _ = agent_id
        if self._knobs.comms_enabled:
            return HIDDEN_CHANNEL_TOOLS
        return HIDDEN_CHANNEL_TOOLS | {"send_message"}

    def runner_prompts(self, agent_id: str) -> RunnerPrompts | None:
        """The workspace protocol: act and observe, message, wait, and finish the round."""
        variables: dict[str, object] = {
            "role_name": seat_role_name(seat=agent_id),
            "can_send": self._knobs.comms_enabled,
        }
        return RunnerPrompts(
            system_suffix=self._renderer.render(
                template_name="protocol_suffix.jinja", template_variables=variables
            ),
            initial=self._renderer.render(
                template_name="protocol_initial.jinja", template_variables=variables
            ),
            continuation=self._renderer.render(
                template_name="protocol_continue.jinja", template_variables=variables
            ),
        )

    async def _act(self, agent: str, command: str, timed: bool) -> str:
        """Run one act; a timed craft returns only once its output has landed.

        The act is refused when the model request that issued it started in a
        round that has since ended: its briefing is stale and the depot is the
        next round's.
        """
        runtime = self.runtime
        requested_round = self._request_round.get(agent)
        if requested_round is None:
            requested_round = runtime.current_round
        virtual_time_s: float | None = None
        async with self._lock:
            if requested_round != runtime.current_round:
                return "Round changed; use your new briefing."
            record, observation = self.world.execute(agent=agent, command=command, timed=timed)
            self._note_virtual_terminal(round_number=requested_round)
            clock = self._clock
            if clock is not None:
                virtual_time_s = clock.round_elapsed_s()
            state = self.world.state
            pending: PendingCraft | None = None
            if record is not None:
                pending = record.pending
            if pending is not None and state is not None:
                # A started craft is logged now; its inbox goes with the landing.
                assert record is not None
                await self._log_action(
                    agent=agent,
                    round_number=requested_round,
                    record=record,
                    state=state,
                    observation=observation,
                    virtual_time_s=virtual_time_s,
                )
            else:
                delivery = self._public_inbox(agent=agent)
                observation = self._with_inbox(observation=observation, delivery=delivery)
                if record is not None and state is not None:
                    await self._log_action(
                        agent=agent,
                        round_number=requested_round,
                        record=record,
                        state=state,
                        observation=observation,
                        virtual_time_s=virtual_time_s,
                    )
                await self._log_inbox(
                    agent=agent,
                    carrier="act",
                    delivery=delivery,
                    round_number=requested_round,
                )
                return observation
        assert state is not None and clock is not None and virtual_time_s is not None
        return await self._land(
            agent=agent,
            state=state,
            pending=pending,
            clock=clock,
            round_number=requested_round,
            started_at_s=virtual_time_s,
        )

    async def _log_action(
        self,
        agent: str,
        round_number: int,
        record: Transition,
        state: DepotState,
        observation: str,
        virtual_time_s: float | None,
    ) -> None:
        """Log one charged ``act`` with the depot it left behind."""
        await self.runtime.event_logger.log(
            event=WorkspaceActionExecuted(
                round_number=round_number,
                agent_id=agent,
                command=record.command,
                accepted=record.accepted,
                version=state.version,
                delta=record.delta,
                depot=dict(state.depot),
                consumed_from=record.consumed_from,
                observation=observation,
                virtual_time_s=virtual_time_s,
            )
        )

    async def _land(
        self,
        agent: str,
        state: DepotState,
        pending: PendingCraft,
        clock: VirtualClock,
        round_number: int,
        started_at_s: float,
    ) -> str:
        """Keep the crafter busy for the craft's duration, then land its output."""
        await clock.occupy(agent_id=agent, duration_s=self._knobs.craft_duration_s)
        runtime = self.runtime
        async with self._lock:
            record = self.world.finish_craft(state=state, pending=pending)
            if record is None:
                return (
                    f"The round ended before the craft of {pending.count} "
                    f"{pending.output} finished."
                )
            self._note_virtual_terminal(round_number=round_number)
            await runtime.event_logger.log(
                event=WorkspaceCraftCompleted(
                    round_number=round_number,
                    agent_id=agent,
                    command=record.command,
                    version=state.version,
                    delta=record.delta,
                    depot=dict(state.depot),
                    started_at_s=started_at_s,
                    virtual_time_s=clock.round_elapsed_s(),
                )
            )
            observation = self.world.observe(agent=agent, action_result=record.observation)
            delivery = self._public_inbox(agent=agent)
            observation = self._with_inbox(observation=observation, delivery=delivery)
            await self._log_inbox(
                agent=agent, carrier="act", delivery=delivery, round_number=round_number
            )
            return observation

    def get_tools(self) -> list[ScenarioTool]:
        """The workspace tools; messaging and waiting are the platform's tools."""

        async def act(agent_id: str, command: str) -> str:
            if self._clock is None or not self._knobs.craft_duration_s:
                return await self._act(agent=agent_id, command=command, timed=False)
            async with self._craft_locks[agent_id]:
                return await self._act(agent=agent_id, command=command, timed=True)

        async def observe(agent_id: str) -> str:
            if self.world.state is None:
                return "Round closed."
            return await self._deliver(
                agent=agent_id, carrier="observe", action_result="Observation."
            )

        act_description = (
            "Apply one exact crafting command to the shared depot. Costs one action; "
            "resources are finite; no get/deposit/withdraw. Results include current "
            "quantities and ordered deltas."
        )
        observe_description = (
            "Free. Return the current depot and the ordered deltas since your last observation."
        )
        if self._knobs.comms_enabled:
            act_description = (
                "Apply one exact crafting command to the shared depot. Costs one action; "
                "resources are finite; no get/deposit/withdraw. Results include current "
                "quantities, ordered deltas and unseen public messages."
            )
            observe_description = (
                "Free. Return the current depot, the ordered deltas since your last "
                "observation, and unseen public messages."
            )
        if self._knobs.uncraft_enabled:
            act_description += (
                " 'uncraft <exact crafting command>' reverses one earlier craft of that "
                "recipe: its output leaves the depot and its inputs return."
            )
        return [
            ScenarioTool(name="act", description=act_description, executor=act),
            ScenarioTool(name="observe", description=observe_description, executor=observe),
        ]


def _lifecycle_entry(notification: ActivityNotification) -> LifecycleEntry | None:
    """A briefing or the end of the run, as a wake reports it; None for anything else."""
    if isinstance(notification, NewInfoNotification):
        return LifecycleEntry(type=notification.type.value, text=notification.text, reason=None)
    if isinstance(notification, DoneNotification):
        return LifecycleEntry(type=notification.type.value, text=None, reason=notification.reason)
    return None


def _audience(channel_id: str, sender: str) -> str:
    """``all`` for the broadcast, otherwise the direct channel's members other than ``sender``."""
    if channel_id == CHANNEL:
        return "all"
    members = channel_id.removeprefix(DIRECT_CHANNEL_PREFIX).split("+")
    return ",".join(member for member in members if member != sender)


def _target_label(item: str, count: int) -> str:
    """A target as the briefing lists it: the item, with ``xN`` when more than one is needed."""
    if count == 1:
        return item
    return f"{item} x{count}"
