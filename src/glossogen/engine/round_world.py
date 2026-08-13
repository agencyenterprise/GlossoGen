"""Per-team character accounting and threshold bookkeeping for budgeted rounds.

Defines ``RoundWorld``, a ``ScenarioWorld`` that charges every message to the
team owning the channel it landed on, counting task channels only, and tracks
which points in the round budget each team has already been told about.

A scenario adds its own budget rule by overriding ``on_message`` and calling up,
which is what makes the total accumulate. ``characters_used`` reads the running
total, ``claim_round_budget_threshold`` answers whether an announcement is still
owed, and ``begin_round`` clears both at a round boundary.
"""

from glossogen.engine.team_declaration import TeamSpec
from glossogen.runtime.scenario_world import ScenarioWorld


class RoundWorld(ScenarioWorld):
    """A world that meters each team's traffic on its own task channel.

    Debrief channels are not metered: a debrief happens after the round is
    scored and does not spend the budget.
    """

    def __init__(
        self,
        team_specs: tuple[TeamSpec, ...],
        round_budget_thresholds: tuple[str, ...],
        postmortem_channel_ids: frozenset[str],
        postmortem_globally_disabled: bool,
    ) -> None:
        """Index the teams by task channel and start every counter at zero.

        ``round_budget_thresholds`` names the points in a round's budget that
        agents are told about, most severe first, and is empty for a scenario
        that announces none. The order is what lets claiming one suppress the
        milder ones beneath it.

        ``postmortem_channel_ids`` covers every mode the scenario can run in,
        not just the debriefs ``team_specs`` declares for this configuration, because
        it is also the set the mid-run swap logic and the replaced-agent history
        filter read. Passing the scenario's class declaration keeps all three
        reading one list.
        """
        super().__init__(
            postmortem_channel_ids=postmortem_channel_ids,
            postmortem_globally_disabled=postmortem_globally_disabled,
        )
        # Which channels cost a team anything. Debrief channels are absent, so
        # a lookup miss is how a message is recognised as free.
        self._task_channel_ids: frozenset[str] = frozenset(
            team.task.channel_id for team in team_specs
        )
        # Which team owns each metered channel. Teams sharing one task channel
        # have no single owner, so this holds only the channels that do.
        self._team_id_by_task_channel_id: dict[str, str] = {
            team.task.channel_id: team.team_id
            for team in team_specs
            if sum(1 for other in team_specs if other.task.channel_id == team.task.channel_id) == 1
        }
        # Who each message costs. A message is charged to its sender's team,
        # which is the only reading that survives two teams sharing a channel.
        self._team_id_by_agent_id: dict[str, str] = {
            role.agent_id: team.team_id for team in team_specs for role in team.roles
        }
        # What each team has spent since ``begin_round``.
        self._characters_used_by_team_id: dict[str, int] = {team.team_id: 0 for team in team_specs}
        # The announcements a round can make, most severe first.
        self._round_budget_thresholds: tuple[str, ...] = round_budget_thresholds
        # Which of those each team has already been told, this round.
        self._claimed_thresholds_by_team_id: dict[str, set[str]] = {
            team.team_id: set() for team in team_specs
        }

    def team_for_task_channel(self, channel_id: str) -> str | None:
        """Return the team that meters ``channel_id``, or None if it is not metered."""
        return self._team_id_by_task_channel_id.get(channel_id)

    def characters_used(self, team_id: str) -> int:
        """Return what ``team_id`` has spent this round."""
        return self._characters_used_by_team_id[team_id]

    def claim_round_budget_threshold(self, team_id: str, round_budget_threshold: str) -> bool:
        """Return True the first time this threshold is owed to ``team_id`` this round.

        Claiming one also claims every milder threshold after it in the declared
        order, so a team told its budget is gone is not then told it is running
        low. Returns False on every later call, which is what makes an
        announcement fire once.
        """
        claimed = self._claimed_thresholds_by_team_id[team_id]
        if round_budget_threshold in claimed:
            return False
        position = self._round_budget_thresholds.index(round_budget_threshold)
        claimed.update(self._round_budget_thresholds[position:])
        return True

    def begin_round(self) -> None:
        """Zero every team's counter and forget what they have been told."""
        for team_id in self._characters_used_by_team_id:
            self._characters_used_by_team_id[team_id] = 0
            self._claimed_thresholds_by_team_id[team_id] = set()

    def on_message(
        self,
        agent_id: str,
        channel_id: str,
        text: str,
        token_count: int,
    ) -> None:
        """Charge a message to its team when it lands on a metered channel.

        Called synchronously from ``send_message`` before the event is enqueued,
        so a scenario's action tool sees the updated total on the same turn the
        message was sent.
        """
        _ = token_count
        if channel_id not in self._task_channel_ids:
            return
        team_id = self._team_id_by_agent_id.get(agent_id)
        if team_id is None:
            return
        self._characters_used_by_team_id[team_id] += len(text)
