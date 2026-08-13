"""The metering, driven directly rather than through a scenario.

A real run does not reach the edges. The scripted agents never send on the
debrief channel, because they exhaust their scripts during the game phase and
are idle by the time the phase opens; and a run's character total lands wherever
it lands, never exactly on the budget. So metering the debrief, or comparing the
budget with the wrong operator, both survive a full veyru run unnoticed.

These drive `RoundWorld` with hand-made messages, where the edges can be asked
for directly.
"""

from glossogen.engine.round_world import RoundWorld
from glossogen.engine.team_declaration import Debrief, RoleSpec, TaskChannel, TeamSpec

DEBRIEF_IDS = frozenset({"debrief_a", "debrief_b"})
# Most severe first, which is the order claiming one suppresses the rest by.
SPENT, LOW = "spent", "low"
ROUND_BUDGET_THRESHOLDS = (SPENT, LOW)


def role(agent_id: str) -> RoleSpec:
    """Build a role; none of these tests vary it."""
    return RoleSpec(
        agent_id=agent_id,
        role_name=agent_id.title(),
        system_template="unused.jinja",
        tool_names=("send_message",),
        joins_debrief=True,
        starts_as_member=True,
    )


def team(team_id: str, task_id: str, debrief_id: str) -> TeamSpec:
    """Build a team with one task channel and one debrief channel."""
    return TeamSpec(
        team_id=team_id,
        task=TaskChannel(channel_id=task_id, name=task_id, display_name="the link"),
        debrief=Debrief(channel_id=debrief_id, name=debrief_id, display_name="the huddle"),
        roles=(role(agent_id=f"{team_id}_worker"),),
    )


TEAMS = (
    team(team_id="a", task_id="task_a", debrief_id="debrief_a"),
    team(team_id="b", task_id="task_b", debrief_id="debrief_b"),
)


def build_world() -> RoundWorld:
    """Build a two-team world with its debrief channels declared."""
    return RoundWorld(
        team_specs=TEAMS,
        round_budget_thresholds=ROUND_BUDGET_THRESHOLDS,
        postmortem_channel_ids=DEBRIEF_IDS,
        postmortem_globally_disabled=False,
    )


def send(world: RoundWorld, agent_id: str, channel_id: str, text: str) -> None:
    """Deliver one message to the world the way ``send_message`` does.

    The sender is named because a message is charged to its team, and a channel
    shared by two teams has no other way to say whose it was.
    """
    world.on_message(agent_id=agent_id, channel_id=channel_id, text=text, token_count=0)


def test_a_team_is_charged_for_what_it_says_on_its_own_channel() -> None:
    """Characters, not tokens or messages, because the budget counts characters."""
    world = build_world()

    send(world=world, agent_id="a_worker", channel_id="task_a", text="12345")
    send(world=world, agent_id="a_worker", channel_id="task_a", text="678")

    assert world.characters_used(team_id="a") == 8


def test_the_debrief_is_not_metered() -> None:
    """A debrief happens after the round is scored and must not spend the budget.

    No scripted run reaches this: agents are idle by the time the phase opens,
    so a world metering its debrief looks correct for an entire simulation.
    """
    world = build_world()

    send(
        world=world,
        agent_id="a_worker",
        channel_id="debrief_a",
        text="a long postmortem discussion",
    )

    assert world.characters_used(team_id="a") == 0


def test_a_channel_nobody_meters_is_ignored() -> None:
    """An unknown channel is not an error and is not charged to anyone."""
    world = build_world()

    send(world=world, agent_id="a_worker", channel_id="some_other_channel", text="chatter")

    assert world.characters_used(team_id="a") == 0
    assert world.characters_used(team_id="b") == 0


def test_teams_are_metered_apart() -> None:
    """Two teams competing on identical cases must not spend each other's budget."""
    world = build_world()

    send(world=world, agent_id="a_worker", channel_id="task_a", text="aaaa")
    send(world=world, agent_id="b_worker", channel_id="task_b", text="bb")

    assert world.characters_used(team_id="a") == 4
    assert world.characters_used(team_id="b") == 2


def test_beginning_a_round_clears_every_team() -> None:
    """A counter surviving the round boundary makes round two start in debt."""
    world = build_world()
    send(world=world, agent_id="a_worker", channel_id="task_a", text="aaaa")
    send(world=world, agent_id="b_worker", channel_id="task_b", text="bb")

    world.begin_round()

    assert world.characters_used(team_id="a") == 0
    assert world.characters_used(team_id="b") == 0


def test_a_threshold_is_owed_once_per_round() -> None:
    """An announcement fired every message would bury the channel in warnings."""
    world = build_world()

    assert world.claim_round_budget_threshold(team_id="a", round_budget_threshold=LOW) is True
    assert world.claim_round_budget_threshold(team_id="a", round_budget_threshold=LOW) is False


def test_claiming_a_severe_threshold_suppresses_the_milder_ones() -> None:
    """Telling a team its budget is gone, then that it is running low, reads backwards."""
    world = build_world()

    assert world.claim_round_budget_threshold(team_id="a", round_budget_threshold=SPENT) is True

    assert world.claim_round_budget_threshold(team_id="a", round_budget_threshold=LOW) is False


def test_a_mild_threshold_does_not_suppress_a_severe_one() -> None:
    """The warning comes first and must not swallow the terminal announcement."""
    world = build_world()

    assert world.claim_round_budget_threshold(team_id="a", round_budget_threshold=LOW) is True

    assert world.claim_round_budget_threshold(team_id="a", round_budget_threshold=SPENT) is True


def test_teams_are_told_independently() -> None:
    """One team hitting its budget says nothing about the other's."""
    world = build_world()

    assert world.claim_round_budget_threshold(team_id="a", round_budget_threshold=SPENT) is True

    assert world.claim_round_budget_threshold(team_id="b", round_budget_threshold=SPENT) is True


def test_beginning_a_round_forgets_what_teams_were_told() -> None:
    """Announcements that carried over would fire once for the whole run."""
    world = build_world()
    world.claim_round_budget_threshold(team_id="a", round_budget_threshold=SPENT)

    world.begin_round()

    assert world.claim_round_budget_threshold(team_id="a", round_budget_threshold=SPENT) is True


def test_the_channel_owner_lookup_answers_only_for_metered_channels() -> None:
    """Scenarios route their own policy through this, so it has to be exact."""
    world = build_world()

    assert world.team_for_task_channel(channel_id="task_a") == "a"
    assert world.team_for_task_channel(channel_id="task_b") == "b"
    assert world.team_for_task_channel(channel_id="debrief_a") is None
    assert world.team_for_task_channel(channel_id="nonexistent") is None


def test_the_total_is_exact_at_the_boundary() -> None:
    """Whether a scenario compares with > or >= is its own rule to make.

    The engine's job is that the number is right at the point the comparison
    happens, so an off-by-one in the metering does not read as an off-by-one in
    someone's budget rule.
    """
    world = build_world()

    send(world=world, agent_id="a_worker", channel_id="task_a", text="x" * 150)

    assert world.characters_used(team_id="a") == 150


def test_the_declared_debrief_channels_are_the_ones_disabled() -> None:
    """The engine must not narrow the set the swap logic and history filter use."""
    world = build_world()

    world.disable_postmortem_globally()

    assert world.get_globally_disabled_channels() == DEBRIEF_IDS


def shared_link_teams() -> tuple[TeamSpec, ...]:
    """Build two teams that talk on one channel and debrief separately."""
    return (
        TeamSpec(
            team_id="a",
            task=TaskChannel(channel_id="link", name="link", display_name="the link"),
            debrief=Debrief(channel_id="debrief_a", name="debrief_a", display_name="the huddle"),
            roles=(role(agent_id="a_worker"),),
        ),
        TeamSpec(
            team_id="b",
            task=TaskChannel(channel_id="link", name="link", display_name="the link"),
            debrief=Debrief(channel_id="debrief_b", name="debrief_b", display_name="the huddle"),
            roles=(role(agent_id="b_worker"),),
        ),
    )


def test_teams_sharing_one_channel_are_charged_for_their_own_words() -> None:
    """Both teams overhear everything, and each pays only for what it said.

    Charging by channel cannot express this: the channel belongs to both, so
    one team would be billed for the other's messages, or for all of them.
    """
    world = RoundWorld(
        team_specs=shared_link_teams(),
        round_budget_thresholds=ROUND_BUDGET_THRESHOLDS,
        postmortem_channel_ids=DEBRIEF_IDS,
        postmortem_globally_disabled=False,
    )

    send(world=world, agent_id="a_worker", channel_id="link", text="aaaa")
    send(world=world, agent_id="b_worker", channel_id="link", text="bb")

    assert world.characters_used(team_id="a") == 4
    assert world.characters_used(team_id="b") == 2
