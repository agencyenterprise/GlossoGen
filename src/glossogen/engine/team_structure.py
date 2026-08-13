"""Derive the runtime's agents, channels and display names from ``TeamSpec`` values.

Each function takes the scenario's declared teams and returns one thing the
runtime needs: the channels with their rosters, the agent configurations with
their prompts rendered, and the display-name maps.
"""

from collections.abc import Callable

from glossogen.engine.team_declaration import Debrief, RoleSpec, TeamSpec
from glossogen.models.agent_config import AgentConfig
from glossogen.models.channel import Channel, ChannelTemplateEntry
from glossogen.models.compaction_config import CompactionConfig

WORLD_SENDER_ID = "world"

# Given a role and the channels it reaches, return that role's system prompt.
# The engine owns which channels a role reaches; the scenario owns what it is
# told about them.
SystemPromptRenderer = Callable[[RoleSpec, list[ChannelTemplateEntry]], str]


def channels(teams: tuple[TeamSpec, ...]) -> list[Channel]:
    """Return each team's task channel, then its debrief channel when it has one.

    Task channels come first across all teams, matching the order scenarios
    build them in today, so a run's channel list does not reorder under the
    engine.
    """
    # Teams may name the same task channel, which is how two of them are put on
    # one link. That is one channel whose roster is both teams, not two.
    rosters: dict[str, list[str]] = {}
    names: dict[str, str] = {}
    for team in teams:
        members = rosters.setdefault(team.task.channel_id, [])
        names[team.task.channel_id] = team.task.name
        members.extend(role.agent_id for role in team.roles if role.starts_as_member)
    built: list[Channel] = [
        Channel(channel_id=channel_id, name=names[channel_id], member_agent_ids=members)
        for channel_id, members in rosters.items()
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

    Teams usually name channels of their own, and two of them calling their link
    "comm link" produce two entries with one display name and different ids,
    which keeps a rejection message readable to either team. Teams sharing a
    link produce one entry, and they had better agree on what to call it.
    """
    names: dict[str, str] = {}
    for team in teams:
        names[team.task.channel_id] = team.task.display_name
        if isinstance(team.debrief, Debrief):
            names[team.debrief.channel_id] = team.debrief.display_name
    return names


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
