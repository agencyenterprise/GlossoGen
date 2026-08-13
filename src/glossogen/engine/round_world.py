"""Per-team character accounting for scenarios with a per-round budget.

Defines ``RoundWorld``, a ``ScenarioWorld`` that charges every message to the
team owning the channel it landed on, counting task channels only. A scenario
adds its own budget rule by overriding ``on_message`` and calling up, which is
what makes the total accumulate; ``characters_used`` reads the running total and
``reset_round_characters`` clears it at a round boundary.
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
        teams: tuple[TeamSpec, ...],
        postmortem_channel_ids: frozenset[str],
        postmortem_globally_disabled: bool,
    ) -> None:
        """Index the teams by task channel and start every counter at zero.

        ``postmortem_channel_ids`` covers every mode the scenario can run in,
        not just the debriefs ``teams`` declares for this configuration, because
        it is also the set the mid-run swap logic and the replaced-agent history
        filter read. Passing the scenario's class declaration keeps all three
        reading one list.
        """
        super().__init__(
            postmortem_channel_ids=postmortem_channel_ids,
            postmortem_globally_disabled=postmortem_globally_disabled,
        )
        self._team_by_task_channel = {team.task.channel_id: team.team_id for team in teams}
        self._characters: dict[str, int] = {team.team_id: 0 for team in teams}

    def team_for_task_channel(self, channel_id: str) -> str | None:
        """Return the team that meters ``channel_id``, or None if it is not metered."""
        return self._team_by_task_channel.get(channel_id)

    def characters_used(self, team_id: str) -> int:
        """Return what ``team_id`` has spent this round."""
        return self._characters[team_id]

    def reset_round_characters(self) -> None:
        """Zero every team's counter, at the start of a round."""
        for team_id in self._characters:
            self._characters[team_id] = 0

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
        _ = agent_id, token_count
        team_id = self._team_by_task_channel.get(channel_id)
        if team_id is None:
            return
        self._characters[team_id] += len(text)
