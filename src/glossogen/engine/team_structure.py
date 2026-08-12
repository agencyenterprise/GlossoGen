"""Derive the runtime's agents, channels and display names from a declaration.

Each scenario currently writes these four derivations by hand, branching on its
own knobs, which is where a two-team layout picks up a role that reaches the
wrong channel. Given ``TeamSpec`` values the derivations are mechanical, so they
are written once here and the scenario states only what its teams are.
"""

from collections.abc import Callable

from glossogen.engine.team_declaration import Debrief, RoleSpec, TeamSpec
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel, ChannelTemplateEntry
from glossogen.models.compaction_config import CompactionConfig

WORLD_SENDER_ID = "world"

# Given a role and the channels it reaches, return that role's system prompt.
# The engine owns which channels a role reaches; the scenario owns what it is
# told about them.
SystemPromptRenderer = Callable[[RoleSpec, list[ChannelTemplateEntry]], str]


def agent_roles(teams: tuple[TeamSpec, ...]) -> list[AgentRole]:
    """Return every role across every team, in declaration order."""
    return [
        AgentRole(agent_id=role.agent_id, role_name=role.role_name)
        for team in teams
        for role in team.roles
    ]


def channels(teams: tuple[TeamSpec, ...]) -> list[Channel]:
    """Return each team's task channel, then its debrief channel when it has one.

    Task channels come first across all teams, matching the order scenarios
    build them in today, so a run's channel list does not reorder under the
    engine.
    """
    built: list[Channel] = [
        Channel(
            channel_id=team.task.channel_id,
            name=team.task.name,
            member_agent_ids=[role.agent_id for role in team.roles if role.starts_as_member],
        )
        for team in teams
    ]
    for team in teams:
        if not isinstance(team.debrief, Debrief):
            continue
        built.append(
            Channel(
                channel_id=team.debrief.channel_id,
                name=team.debrief.name,
                member_agent_ids=[
                    role.agent_id
                    for role in team.roles
                    if role.joins_debrief and role.starts_as_member
                ],
            )
        )
    return built


def agent_display_names(teams: tuple[TeamSpec, ...], world_name: str) -> dict[str, str]:
    """Map every agent id to its role name, plus the world's own sender name."""
    names = {role.agent_id: role.role_name for team in teams for role in team.roles}
    names[WORLD_SENDER_ID] = world_name
    return names


def channel_display_names(teams: tuple[TeamSpec, ...]) -> dict[str, str]:
    """Map each channel id to the name agents are told to call it.

    Teams name their own channels, so two teams that both call their link "comm
    link" produce two entries with the same display name and different ids,
    which is what keeps a rejection message readable to either team.
    """
    names: dict[str, str] = {}
    for team in teams:
        names[team.task.channel_id] = team.task.display_name
        if isinstance(team.debrief, Debrief):
            names[team.debrief.channel_id] = team.debrief.display_name
    return names


def task_channel_ids(teams: tuple[TeamSpec, ...]) -> frozenset[str]:
    """Return the channels the engine meters, corrupts and shuts during debrief."""
    return frozenset(team.task.channel_id for team in teams)


def debrief_channel_ids(teams: tuple[TeamSpec, ...]) -> frozenset[str]:
    """Return the channels that only accept traffic while the phase is open."""
    return frozenset(team.debrief.channel_id for team in teams if isinstance(team.debrief, Debrief))


def team_id_by_channel(teams: tuple[TeamSpec, ...]) -> dict[str, str]:
    """Map every channel id to the team that owns it, for per-team accounting."""
    owners: dict[str, str] = {}
    for team in teams:
        owners[team.task.channel_id] = team.team_id
        if isinstance(team.debrief, Debrief):
            owners[team.debrief.channel_id] = team.team_id
    return owners


def build_agent_configs(
    teams: tuple[TeamSpec, ...],
    render_system_prompt: SystemPromptRenderer,
    default_model: str,
    default_provider: str,
    max_tokens: int,
    compaction: CompactionConfig,
) -> list[AgentConfig]:
    """Return one ``AgentConfig`` per declared role, with its prompt rendered.

    ``render_system_prompt`` receives the role and the channels it reaches, and
    returns the prompt text. Prompt content stays with the scenario, since what
    a role is told is the scenario's subject matter; only the wiring is derived
    here.
    """
    configs: list[AgentConfig] = []
    for team in teams:
        for role in team.roles:
            channel_ids = team.channel_ids_for(role=role)
            configs.append(
                AgentConfig(
                    agent_id=role.agent_id,
                    role_name=role.role_name,
                    system_prompt=render_system_prompt(
                        role, _template_entries(team=team, role=role)
                    ),
                    channel_ids=list(channel_ids),
                    tool_names=list(role.tool_names),
                    model=default_model,
                    provider=default_provider,
                    max_tokens=max_tokens,
                    compaction=compaction,
                )
            )
    return configs


def _template_entries(team: TeamSpec, role: RoleSpec) -> list[ChannelTemplateEntry]:
    """Return the channel entries a role's system-prompt template renders over."""
    display = channel_display_names(teams=(team,))
    return [
        ChannelTemplateEntry(display_name=display[channel_id], channel_id=channel_id)
        for channel_id in team.channel_ids_for(role=role)
    ]
