"""The derivations, exercised on declarations no shipped scenario produces yet.

The veyru equivalence tests cover the derivations against a real scenario, but
only through the combinations veyru happens to use. Veyru's intern is its only
role that skips the debrief and its only role that arrives late, so those two
flags always move together there and a derivation that confused them would pass.

These drive every combination of the two directly. A scenario that later wants a
role present from round one but excluded from the debrief, an eavesdropper on the
task channel, say, gets a derivation that was already correct rather than one
that happened to work.
"""

from glossogen.engine import team_structure
from glossogen.engine.team_declaration import (
    Debrief,
    NoDebrief,
    RoleSpec,
    TaskChannel,
    TeamSpec,
)

TASK = TaskChannel(channel_id="task", name="task", display_name="the floor")
DEBRIEF = Debrief(channel_id="debrief", name="debrief", display_name="the huddle")


def role(agent_id: str, joins_debrief: bool, starts_as_member: bool) -> RoleSpec:
    """Build a role varying only the two flags under test."""
    return RoleSpec(
        agent_id=agent_id,
        role_name=agent_id.title(),
        system_template="unused.jinja",
        tool_names=("send_message",),
        joins_debrief=joins_debrief,
        starts_as_member=starts_as_member,
    )


FULL = role(agent_id="full", joins_debrief=True, starts_as_member=True)
TASK_ONLY = role(agent_id="task_only", joins_debrief=False, starts_as_member=True)
LATE = role(agent_id="late", joins_debrief=True, starts_as_member=False)
LATE_TASK_ONLY = role(agent_id="late_task_only", joins_debrief=False, starts_as_member=False)

TEAM = TeamSpec(
    team_id="solo",
    task=TASK,
    debrief=DEBRIEF,
    roles=(FULL, TASK_ONLY, LATE, LATE_TASK_ONLY),
)


def members_of(channel_id: str) -> list[str]:
    """Return the roster the engine derives for one channel."""
    for channel in team_structure.channels(teams=(TEAM,)):
        if channel.channel_id == channel_id:
            return channel.member_agent_ids
    raise AssertionError(f"{channel_id} was not built")


def test_the_task_roster_is_everyone_present_from_the_start() -> None:
    """Skipping the debrief does not keep a role off the task channel."""
    assert members_of(channel_id="task") == ["full", "task_only"]


def test_the_debrief_roster_needs_both_present_and_attending() -> None:
    """A role present but not attending is the case veyru cannot produce.

    Without it, filtering the debrief roster on presence alone gives the right
    answer for every shipped layout and the wrong one for the first scenario
    that wants a silent observer.
    """
    assert members_of(channel_id="debrief") == ["full"]


def test_a_role_that_attends_but_arrives_late_is_in_neither_roster_yet() -> None:
    """Arriving late means arriving late to both."""
    assert "late" not in members_of(channel_id="task")
    assert "late" not in members_of(channel_id="debrief")


def test_every_role_is_configured_for_its_channels_whether_or_not_it_has_arrived() -> None:
    """Reach is fixed at construction; the roster is what changes mid-run.

    A late arrival still needs its channels on its agent config, because that is
    what shapes its system prompt and what it may address once it does arrive.
    """
    reach = {role_spec.agent_id: TEAM.channel_ids_for(role=role_spec) for role_spec in TEAM.roles}

    assert reach["full"] == ("task", "debrief")
    assert reach["task_only"] == ("task",)
    assert reach["late"] == ("task", "debrief")
    assert reach["late_task_only"] == ("task",)


def test_a_team_without_a_debrief_builds_only_its_task_channel() -> None:
    """`NoDebrief` is the author saying so, and nothing downstream looks for one."""
    team = TeamSpec(team_id="solo", task=TASK, debrief=NoDebrief(), roles=(FULL,))

    built = team_structure.channels(teams=(team,))

    assert [c.channel_id for c in built] == ["task"]
    assert team.channel_ids_for(role=FULL) == ("task",)


def test_two_teams_keep_their_channels_and_rosters_apart() -> None:
    """Two teams must not share a channel id, or per-team accounting merges them."""
    team_a = TeamSpec(team_id="a", task=TASK, debrief=DEBRIEF, roles=(FULL,))
    team_b = TeamSpec(
        team_id="b",
        task=TaskChannel(channel_id="task_b", name="task_b", display_name="the floor"),
        debrief=Debrief(channel_id="debrief_b", name="debrief_b", display_name="the huddle"),
        roles=(role(agent_id="other", joins_debrief=True, starts_as_member=True),),
    )
    teams = (team_a, team_b)

    built = team_structure.channels(teams=teams)

    assert [c.channel_id for c in built] == ["task", "task_b", "debrief", "debrief_b"]
    assert [c.member_agent_ids for c in built] == [["full"], ["other"], ["full"], ["other"]]
