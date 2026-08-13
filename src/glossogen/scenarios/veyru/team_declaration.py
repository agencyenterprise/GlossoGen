"""Veyru's structure, stated as engine declarations rather than built by hand.

Veyru runs in two layouts. Single-team is one comm link staffed by an observer
and an engineer, optionally joined by an intern. Two-team is two isolated
copies of that pairing which never see each other's channel. Either layout may
carry the post-round discussion.

Everything the runtime needs, the agent list, the channel list, the display-name
maps, which channels are metered and which are debriefs, is derived from what
this returns.
"""

from typing import NamedTuple

from glossogen.engine.team_declaration import (
    Debrief,
    DebriefPolicy,
    NoDebrief,
    RoleSpec,
    TaskChannel,
    TeamSpec,
)
from glossogen.scenarios.veyru.ids import (
    FIELD_OBSERVER_A_ROLE,
    FIELD_OBSERVER_B_ROLE,
    FIELD_OBSERVER_ID,
    FIELD_OBSERVER_ROLE,
    FIELD_OBSERVER_SYSTEM_TEMPLATE,
    INTERN_ID,
    INTERN_ROLE,
    INTERN_SYSTEM_TEMPLATE,
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
    OBSERVER_A_ID,
    OBSERVER_B_ID,
    POSTMORTEM_A_CHANNEL_ID,
    POSTMORTEM_B_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
    STABILIZATION_ENGINEER_A_ID,
    STABILIZATION_ENGINEER_A_ROLE,
    STABILIZATION_ENGINEER_B_ID,
    STABILIZATION_ENGINEER_B_ROLE,
    STABILIZATION_ENGINEER_ID,
    STABILIZATION_ENGINEER_ROLE,
    STABILIZATION_ENGINEER_SYSTEM_TEMPLATE,
    TEAM_A_ID,
    TEAM_B_ID,
    TEAM_SOLO_ID,
    TOOLS_INTERN,
    TOOLS_OBSERVER,
    TOOLS_STABILIZATION_ENGINEER,
    TeamId,
)
from glossogen.scenarios.veyru.knobs import VeyruKnobs
from glossogen.scenarios.veyru.world_state import TeamState

LINK_DISPLAY_NAME = "comm link"
DEBRIEF_DISPLAY_NAME = "team discussion"
WORLD_DISPLAY_NAME = "Veyru Monitor"


def _debrief(channel_id: str, name: str, active: bool) -> DebriefPolicy:
    """Return the debrief policy for a channel that may be switched off."""
    if not active:
        return NoDebrief()
    return Debrief(channel_id=channel_id, name=name, display_name=DEBRIEF_DISPLAY_NAME)


def _observer(agent_id: str, role_name: str) -> RoleSpec:
    """Return an observer role: it can send, and it can stabilize."""
    return RoleSpec(
        agent_id=agent_id,
        role_name=role_name,
        system_template=FIELD_OBSERVER_SYSTEM_TEMPLATE,
        tool_names=tuple(TOOLS_OBSERVER),
        joins_debrief=True,
        starts_as_member=True,
    )


def _engineer(agent_id: str, role_name: str) -> RoleSpec:
    """Return an engineer role: it can send, and nothing else."""
    return RoleSpec(
        agent_id=agent_id,
        role_name=role_name,
        system_template=STABILIZATION_ENGINEER_SYSTEM_TEMPLATE,
        tool_names=tuple(TOOLS_STABILIZATION_ENGINEER),
        joins_debrief=True,
        starts_as_member=True,
    )


def _intern(joins_debrief: bool) -> RoleSpec:
    """Return the intern role.

    The intern reaches the discussion channel only when the run keeps a
    postmortem past the takeover; otherwise it sits on the comm link alone.

    It is configured for the comm link from round one but is not in the
    channel's roster until ``intern_join_round`` fires, so it cannot read the
    traffic it is meant to arrive after.
    """
    return RoleSpec(
        agent_id=INTERN_ID,
        role_name=INTERN_ROLE,
        system_template=INTERN_SYSTEM_TEMPLATE,
        tool_names=tuple(TOOLS_INTERN),
        joins_debrief=joins_debrief,
        starts_as_member=False,
    )


class _TeamLayout(NamedTuple):
    """One team's seats and channels, before either projection is taken.

    ``veyru_teams`` turns these into the engine's ``TeamSpec`` values and
    ``veyru_team_states`` into the world's ``TeamState``. Both read this, so
    neither can name a channel or a seat the other does not.
    """

    team_id: TeamId
    link_channel_id: str
    link_channel_name: str
    postmortem_channel_id: str
    postmortem_channel_name: str
    observer_id: str
    observer_role: str
    engineer_id: str
    engineer_role: str


def _layouts(knobs: VeyruKnobs) -> tuple[_TeamLayout, ...]:
    """Return the layout of every team this configuration runs."""
    if knobs.two_teams:
        return (
            _TeamLayout(
                team_id=TEAM_A_ID,
                link_channel_id=LINK_A_CHANNEL_ID,
                link_channel_name="link_a",
                postmortem_channel_id=POSTMORTEM_A_CHANNEL_ID,
                postmortem_channel_name="postmortem_a",
                observer_id=OBSERVER_A_ID,
                observer_role=FIELD_OBSERVER_A_ROLE,
                engineer_id=STABILIZATION_ENGINEER_A_ID,
                engineer_role=STABILIZATION_ENGINEER_A_ROLE,
            ),
            _TeamLayout(
                team_id=TEAM_B_ID,
                link_channel_id=LINK_B_CHANNEL_ID,
                link_channel_name="link_b",
                postmortem_channel_id=POSTMORTEM_B_CHANNEL_ID,
                postmortem_channel_name="postmortem_b",
                observer_id=OBSERVER_B_ID,
                observer_role=FIELD_OBSERVER_B_ROLE,
                engineer_id=STABILIZATION_ENGINEER_B_ID,
                engineer_role=STABILIZATION_ENGINEER_B_ROLE,
            ),
        )
    return (
        _TeamLayout(
            team_id=TEAM_SOLO_ID,
            link_channel_id=LINK_CHANNEL_ID,
            link_channel_name="link",
            postmortem_channel_id=POSTMORTEM_CHANNEL_ID,
            postmortem_channel_name="postmortem",
            observer_id=FIELD_OBSERVER_ID,
            observer_role=FIELD_OBSERVER_ROLE,
            engineer_id=STABILIZATION_ENGINEER_ID,
            engineer_role=STABILIZATION_ENGINEER_ROLE,
        ),
    )


def veyru_teams(knobs: VeyruKnobs) -> tuple[TeamSpec, ...]:
    """Return the teams this configuration runs, one per isolated comm link."""
    debrief_active = knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
    specs: list[TeamSpec] = []
    for layout in _layouts(knobs=knobs):
        roles = [
            _observer(agent_id=layout.observer_id, role_name=layout.observer_role),
            _engineer(agent_id=layout.engineer_id, role_name=layout.engineer_role),
        ]
        if not knobs.two_teams and knobs.intern_enabled:
            roles.append(
                _intern(joins_debrief=knobs.postmortem_enabled and knobs.postmortem_after_swap)
            )
        specs.append(
            TeamSpec(
                team_id=layout.team_id,
                task=TaskChannel(
                    channel_id=layout.link_channel_id,
                    name=layout.link_channel_name,
                    display_name=LINK_DISPLAY_NAME,
                ),
                debrief=_debrief(
                    channel_id=layout.postmortem_channel_id,
                    name=layout.postmortem_channel_name,
                    active=debrief_active,
                ),
                roles=tuple(roles),
            )
        )
    return tuple(specs)


def veyru_team_states(knobs: VeyruKnobs) -> dict[TeamId, TeamState]:
    """Return the world's per-team state for this configuration.

    The seats come off the layout rather than being read back out of the specs,
    so who observes for a team is a fact the declaration states, not one
    inferred from which prompt file a role renders.
    """
    debrief_active = knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
    states: dict[TeamId, TeamState] = {}
    for layout in _layouts(knobs=knobs):
        if debrief_active:
            postmortem_channel_id: str | None = layout.postmortem_channel_id
        else:
            postmortem_channel_id = None
        states[layout.team_id] = TeamState(
            team_id=layout.team_id,
            current_observer_id=layout.observer_id,
            stabilization_engineer_id=layout.engineer_id,
            link_channel_id=layout.link_channel_id,
            postmortem_channel_id=postmortem_channel_id,
        )
    return states
