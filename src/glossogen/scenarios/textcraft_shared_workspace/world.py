"""Round lifecycle and communication, action and token budgets around the shared depot."""

import math

from glossogen.engine.round_world import RoundWorld
from glossogen.engine.team_declaration import NoDebrief, RoleSpec, TaskChannel, TeamSpec
from glossogen.runners.communication_protocol import (
    FINISH_TOOL_NAME,
    SEND_TOOL_NAME,
    WAIT_FOR_MESSAGE_TOOL_NAME,
)
from glossogen.scenarios.textcraft_shared_workspace.knobs import SharedWorkspaceKnobs
from glossogen.scenarios.textcraft_shared_workspace.state import (
    DepotState,
    PendingCraft,
    Transition,
)
from glossogen.scenarios.textcraft_shared_workspace.tasks import WorkspaceTask

CHANNEL = "workspace"
TEAM = "workspace"

PSEUDO_COMMANDS = ("depot", "wait")
"""``act`` commands from TextCraft that are not crafts; ``observe`` and the
suspension tools replace them, so they are refused without costing an action."""


def seat_ids(agent_count: int) -> list[str]:
    """The agents that take part, ``crafter_1`` onward."""
    return [f"crafter_{i + 1}" for i in range(agent_count)]


def seat_role_name(seat: str) -> str:
    """Display name of an agent."""
    return seat.replace("crafter_", "Crafter ")


def workspace_tool_names(comms_enabled: bool) -> tuple[str, ...]:
    """The tools each agent is offered; without messaging, neither ``send`` nor waiting."""
    if not comms_enabled:
        return ("act", "observe", FINISH_TOOL_NAME)
    return (SEND_TOOL_NAME, "act", "observe", WAIT_FOR_MESSAGE_TOOL_NAME, FINISH_TOOL_NAME)


def is_pseudo_command(command: str) -> bool:
    """True for ``depot``, ``wait`` and ``think:`` commands, which move no resources."""
    stripped = command.strip()
    return stripped in PSEUDO_COMMANDS or stripped.startswith("think:")


def workspace_teams(seats: list[str], comms_enabled: bool) -> tuple[TeamSpec, ...]:
    """One broadcast channel; no direct channels or free debrief."""
    return (
        TeamSpec(
            team_id=TEAM,
            task=TaskChannel(
                channel_id=CHANNEL, name="workspace broadcast", display_name="workspace broadcast"
            ),
            debrief=NoDebrief(),
            roles=tuple(
                RoleSpec(
                    agent_id=seat,
                    role_name=seat_role_name(seat=seat),
                    system_template="crafter_system.jinja",
                    tool_names=workspace_tool_names(comms_enabled=comms_enabled),
                    joins_debrief=False,
                    starts_as_member=True,
                )
                for seat in seats
            ),
        ),
    )


class SharedWorkspaceWorld(RoundWorld):
    """Finite resources and one team-wide pool of workspace actions."""

    def __init__(self, knobs: SharedWorkspaceKnobs) -> None:
        self.seats = seat_ids(agent_count=knobs.agent_count)
        super().__init__(
            team_specs=workspace_teams(seats=self.seats, comms_enabled=knobs.comms_enabled),
            round_budget_thresholds=(),
            postmortem_channel_ids=frozenset(),
            postmortem_globally_disabled=True,
        )
        self.knobs = knobs
        self.state: DepotState | None = None
        self.actions: dict[str, int] = {}
        self.action_allowance = 0
        self.tokens_used = 0
        self.closed = True

    def team_action_allowance(self, task: WorkspaceTask) -> int:
        """Workspace action attempts the whole team gets for ``task``.

        Each column gets ``actions_per_witness_step`` times its share of the
        witness, rounded up, and the team pools every column's attempts.
        """
        per_column = math.ceil(
            self.knobs.actions_per_witness_step * len(task.witness) / len(task.cards)
        )
        return per_column * len(task.cards)

    def start(self, task: WorkspaceTask) -> None:
        """Clear resources, observation cursors, and budgets at the round boundary."""
        self.begin_round()
        self.state = DepotState(
            task=task,
            seats=self.seats,
            uncraft_enabled=self.knobs.uncraft_enabled,
        )
        self.actions = dict.fromkeys(self.seats, 0)
        self.action_allowance = self.team_action_allowance(task=task)
        self.tokens_used = 0
        self.closed = False

    def actions_left(self) -> int:
        """Attempts the team may still make."""
        return self.action_allowance - sum(self.actions.values())

    def record_model_usage(self, tokens: int) -> None:
        """Charge one model response's prompt and completion tokens to the open round."""
        if self.closed or self.state is None:
            return
        self.tokens_used += tokens

    @property
    def tokens_exhausted(self) -> bool:
        """True once the team has spent more than ``team_token_limit`` this round."""
        limit = self.knobs.team_token_limit
        return limit is not None and self.tokens_used > limit

    @property
    def budget_exceeded(self) -> bool:
        """Exact-cap usage is allowed; crossing it makes the round unaffordable."""
        cap = self.knobs.round_time_budget_seconds
        return cap >= 0 and self.characters_used(TEAM) > cap

    @property
    def terminal_trigger(self) -> str | None:
        """The tool and clock consult the same terminal rule."""
        if self.state is None:
            return None
        if self.budget_exceeded:
            return "budget_exhausted"
        if self.state.solved:
            return "all_targets_satisfied"
        if not self.state.in_progress and self.actions_left() <= 0:
            # A started craft still lands, so spent actions end the round after it.
            return "actions_exhausted"
        if self.tokens_exhausted:
            return "team_tokens_exhausted"
        return None

    def execute(self, agent: str, command: str, timed: bool) -> tuple[Transition | None, str]:
        """Charge one action and run ``command``.

        With ``timed``, an accepted craft only starts and ``finish_craft`` lands it.
        """
        if self.closed or self.state is None or self.terminal_trigger is not None:
            return None, "Round closed."
        if agent not in self.actions:
            return None, "Unknown crafter."
        if self.actions_left() <= 0:
            return None, "No actions remaining."
        if is_pseudo_command(command):
            return None, (
                "act only accepts crafting commands. Use observe() to inspect the depot; "
                "it costs no action."
            )
        self.actions[agent] += 1
        if timed:
            record = self.state.start(agent_id=agent, command=command)
        else:
            record = self.state.step(agent_id=agent, command=command)
        return record, self.observe(agent=agent, action_result=record.observation)

    def finish_craft(self, state: DepotState, pending: PendingCraft) -> Transition | None:
        """Land a craft started on ``state``; None once that round's depot is gone."""
        if self.state is not state or self.closed:
            return None
        return state.finish(pending=pending)

    def observe(self, agent: str, action_result: str) -> str:
        """Build an agent's observation after an action, a send, a wake or ``observe``."""
        if self.state is None:
            return "Round closed."
        view = self.state.observe(agent)
        cap = self.knobs.round_time_budget_seconds
        budget = "unlimited"
        if cap != -1:
            budget = str(max(0, cap - self.characters_used(TEAM)))
        status = self.terminal_trigger
        if status is None:
            status = "active"
            if self.closed:
                status = "closed"
        return (
            f"{action_result}\n{view}\nTeam actions remaining: {self.actions_left()}. "
            f"Broadcast characters remaining: {budget}.\nRound status: {status}."
        )
