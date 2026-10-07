"""A team crafts every target of a layered recipe grid from one finite shared depot."""

import asyncio
import random
from collections import Counter
from pathlib import Path
from typing import Any, Literal, NamedTuple

from glossogen.engine import team_structure
from glossogen.engine.team_declaration import RoleSpec
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel, ChannelTemplateEntry
from glossogen.models.message import SimulationMessage
from glossogen.models.public_message_block import NO_PUBLIC_MESSAGES, PUBLIC_MESSAGES_HEADER
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from glossogen.runtime.virtual_clock import VirtualClock, VirtualClockConfig
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.channel_noise import apply_character_noise
from glossogen.scenarios.textcraft_shared_workspace.events import (
    WorkspaceActionExecuted,
    WorkspaceCraftCompleted,
    WorkspaceMessageContextDelivered,
    WorkspaceRecipesDealt,
    WorkspaceRoundResolved,
    WorkspaceTaskStarted,
)
from glossogen.scenarios.textcraft_shared_workspace.knobs import SharedWorkspaceKnobs
from glossogen.scenarios.textcraft_shared_workspace.recipe_dealing import deal_recipes
from glossogen.scenarios.textcraft_shared_workspace.state import DepotState, PendingCraft
from glossogen.scenarios.textcraft_shared_workspace.tasks import (
    WorkspaceTask,
    generate_task,
    load_task_manifest,
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
        """Resolve symmetric seats before a runtime exists."""
        values = knobs or {}
        agent_count = int(values.get("crafter_count", 3))
        if values.get("pool_agent_count") is not None:
            agent_count = int(values["pool_agent_count"])
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
        """Build one agent per seat, all on the ``workspace_action`` protocol."""
        agents = team_structure.build_agent_configs(
            teams=self._teams,
            render_system_prompt=self._system,
            default_model=default_model,
            default_provider=default_provider,
            max_tokens=self._knobs.agent_max_tokens,
            compaction=self._knobs.compaction,
            send_back_thinking=self._knobs.send_back_thinking,
        )
        for agent in agents:
            agent.interaction_protocol = "workspace_action"
        return agents

    def get_virtual_clock_config(self) -> VirtualClockConfig | None:
        """Simulate hosted-API latency when the ``virtual_clock`` knob asks for it."""
        if not self._knobs.virtual_clock:
            return None
        return VirtualClockConfig(
            base_latency_s=self._knobs.virtual_base_latency_s,
            output_tokens_per_second=self._knobs.virtual_output_tokens_per_second,
        )

    def on_model_usage(self, agent_id: str, input_tokens: int, output_tokens: int) -> None:
        """Charge each released response to the team token pool, when one is set."""
        _ = agent_id
        if self._knobs.team_token_limit is None or self._runtime is None:
            return
        self.world.record_model_usage(tokens=input_tokens + output_tokens)
        self._note_virtual_terminal(round_number=self._runtime.current_round)

    def _virtual_clock(self) -> VirtualClock | None:
        """The runtime's virtual clock, or None offline or at wall-clock pace."""
        if not self._knobs.virtual_clock or self._runtime is None:
            return None
        return self._runtime.virtual_clock

    def _note_virtual_terminal(self, round_number: int) -> None:
        """Remember the virtual instant this round first met a terminal condition."""
        clock = self._virtual_clock()
        if clock is None or round_number in self._virtual_terminal_at:
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
        """Keep silent conditions present in generic communication metrics."""
        return [PrimaryChannel(channel_id=CHANNEL, team_id=None)]

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
                    item if count == 1 else f"{item} x{count}"
                    for item, count in sorted(targets.items())
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
            self.world.start(task)
            clock = self._virtual_clock()
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
                characters_used=self.world.characters_used(TEAM),
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
        clock = self._virtual_clock()
        if clock is None:
            return None
        return self._virtual_terminal_at.get(round_number, clock.round_elapsed_s())

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Close action and message admission and write the deterministic outcome."""
        async with self._lock:
            self.world.closed = True
            await self.runtime.event_logger.log(event=self._result(round_number, trigger))

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """No LLM judge; targets coexist and speech stays within budget."""
        result = self._result(round_number, trigger)
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
        """Accept only the workspace broadcast, while messaging is on and the round open."""
        if channel_id != CHANNEL or agent_id not in self.world.seats:
            return "Only the workspace public broadcast is available."
        if not self._knobs.comms_enabled:
            return "Broadcast is disabled in this condition."
        if self.world.closed or self.world.terminal_trigger is not None:
            return "Round closed."
        return None

    def transform_outgoing_message(self, agent_id: str, channel_id: str, text: str) -> str:
        """Use the platform's noise mechanism on the metered channel."""
        _ = agent_id
        if channel_id != CHANNEL:
            return text
        return apply_character_noise(
            text=text,
            noise_level=self._knobs.channel_noise_level,
            mode=self._knobs.noise_replacement_mode,
            rng=self._noise_rng,
        )

    def _public_inbox(self, agent: str) -> PublicInboxDelivery:
        """Drain the agent's unread public messages and render them for a tool result.

        The agent's own messages advance its cursor but are never rendered back.
        An agent that cannot message is told nothing about messages.
        """
        if not self._knobs.comms_enabled:
            return PublicInboxDelivery(messages=[], rendered="")
        messages = [
            message
            for message in self.runtime.drain_unread_channel_messages(
                agent_id=agent,
                channel_id=CHANNEL,
            )
            if message.sender_agent_id != agent
        ]
        if not messages:
            return PublicInboxDelivery(
                messages=[], rendered=f"{PUBLIC_MESSAGES_HEADER}\n{NO_PUBLIC_MESSAGES}"
            )
        lines = [PUBLIC_MESSAGES_HEADER]
        for message in messages:
            audience = "all"
            if message.recipient_agent_ids:
                audience = ",".join(message.recipient_agent_ids)
            metadata = f"; id={message.message_id}; to={audience}"
            if message.reply_to:
                metadata += f"; reply_to={message.reply_to}"
            lines.append(
                f"[round {message.round_number}; "
                f"{message.sender_display_name} via {CHANNEL}{metadata}] {message.text}"
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
        if not delivery.messages:
            return
        await self.runtime.event_logger.log(
            event=WorkspaceMessageContextDelivered(
                round_number=round_number,
                agent_id=agent,
                channel_id=CHANNEL,
                delivery_carrier=carrier,
                message_ids=[message.message_id for message in delivery.messages],
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
        logs the delivery. ``send``, ``observe`` and wake-ups all go through here
        so a message is delivered exactly once whichever carried it.
        """
        async with self._lock:
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

    async def deliver_wake_context(self, agent_id: str, wake_reasons: list[str]) -> str | None:
        """The workspace part of a wake package."""
        if self.world.state is None:
            return None
        return await self._deliver(
            agent=agent_id,
            carrier="wake",
            action_result=f"Woke: {', '.join(wake_reasons)}.",
        )

    async def deliver_send_context(self, agent_id: str, channel_id: str) -> str | None:
        """The observation attached to a send receipt."""
        _ = channel_id
        if self.world.state is None:
            return None
        return await self._deliver(agent=agent_id, carrier="send", action_result="Message sent.")

    async def _act(self, agent: str, command: str, timed: bool) -> str:
        """Run one act; a timed craft returns only once its output has landed."""
        runtime = self._runtime
        requested_round = 0
        if runtime is not None:
            requested_round = runtime.current_round
        virtual_time_s: float | None = None
        async with self._lock:
            if runtime is not None and requested_round != runtime.current_round:
                return "Round changed; use your new briefing."
            record, observation = self.world.execute(agent=agent, command=command, timed=timed)
            self._note_virtual_terminal(round_number=requested_round)
            clock = self._virtual_clock()
            if clock is not None:
                virtual_time_s = clock.round_elapsed_s()
            state = self.world.state
            pending: PendingCraft | None = None
            if record is not None:
                pending = record.pending
            if pending is not None and state is not None and runtime is not None:
                # A started craft is logged now; its inbox goes with the landing.
                assert record is not None
                await runtime.event_logger.log(
                    event=WorkspaceActionExecuted(
                        round_number=requested_round,
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
            else:
                delivery = self._public_inbox(agent=agent)
                observation = self._with_inbox(observation=observation, delivery=delivery)
                if record is not None and state is not None and runtime is not None:
                    await runtime.event_logger.log(
                        event=WorkspaceActionExecuted(
                            round_number=requested_round,
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
                if runtime is not None:
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

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """The workspace tools; ``send`` and the suspension tools come from the runtime."""

        async def act(ctx: ToolContext, command: str) -> str:
            agent = resolve_agent_id(ctx=ctx)
            if self._virtual_clock() is None or not self._knobs.craft_duration_s:
                return await self._act(agent=agent, command=command, timed=False)
            async with self._craft_locks[agent]:
                return await self._act(agent=agent, command=command, timed=True)

        async def observe(ctx: ToolContext, note: str | None = None) -> str:
            # ``note`` is ignored; see ``read_notifications`` for why it exists.
            _ = note
            agent = resolve_agent_id(ctx=ctx)
            if self.world.state is None:
                return "Round closed."
            return await self._deliver(agent=agent, carrier="observe", action_result="Observation.")

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
            ScenarioMcpTool(name="act", description=act_description, executor=act),
            ScenarioMcpTool(name="observe", description=observe_description, executor=observe),
        ]
