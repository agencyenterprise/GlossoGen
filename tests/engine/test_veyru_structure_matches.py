"""The declared structure has to be the structure veyru already builds.

Before any of veyru's round mechanics move to the engine, the engine has to
derive the same agents, channels and memberships that `agent_factory` builds by
hand. That is the cheap half of the migration to verify and the half that breaks
silently: an agent wired to one channel too few still runs, still logs, and just
never hears from its team.

Every knob combination that changes the roster is covered, because the layouts
differ structurally rather than by degree, and the two-team layout is where a
role reaching the wrong channel would actually be observable.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from glossogen.engine import team_structure
from glossogen.engine.team_declaration import Debrief, RoleSpec
from glossogen.models.channel import Channel, ChannelTemplateEntry
from glossogen.scenarios.veyru.agent_factory import build_agents, build_channels
from glossogen.scenarios.veyru.knobs import VeyruKnobs
from glossogen.scenarios.veyru.scenario import PROMPTS_DIR
from glossogen.scenarios.veyru.team_declaration import veyru_teams
from glossogen.template_renderer import TemplateRenderer

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "src" / "glossogen" / "scenarios"

LAYOUTS: dict[str, dict[str, Any]] = {
    "single team": {"two_teams": False},
    "single team, no debrief": {
        "two_teams": False,
        "postmortem_enabled": False,
        "postmortem_after_swap": False,
    },
    "single team with intern": {
        "two_teams": False,
        "intern_enabled": True,
        "intern_join_round": 2,
        "intern_takeover_round": 3,
    },
    "single team with intern, debrief closed after takeover": {
        "two_teams": False,
        "intern_enabled": True,
        "intern_join_round": 2,
        "intern_takeover_round": 3,
        "postmortem_after_swap": False,
    },
    "two teams": {"two_teams": True, "swap_round": 2},
    "two teams, no debrief": {
        "two_teams": True,
        "swap_round": 2,
        "postmortem_enabled": False,
        "postmortem_after_swap": False,
    },
}


def knobs_for(overrides: dict[str, Any]) -> VeyruKnobs:
    """Build veyru knobs from the shipped preset plus a layout's overrides."""
    config = json.loads((SCENARIOS_DIR / "veyru" / "knobs_default.json").read_text())
    config.update(overrides)
    return VeyruKnobs.model_validate(config)


def as_comparable(channels: list[Channel]) -> list[tuple[str, str, tuple[str, ...]]]:
    """Reduce channels to id, name and membership, which is what has to match."""
    return [(c.channel_id, c.name, tuple(c.member_agent_ids)) for c in channels]


def no_prompt(role: RoleSpec, channels: list[ChannelTemplateEntry]) -> str:
    """Render nothing.

    Prompt text is the scenario's own and is compared by the runtime tests that
    render it for real; what these check is the wiring around it.
    """
    _ = role, channels
    return ""


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
def test_the_declaration_builds_the_same_channels(layout: str) -> None:
    """Same ids, same names, same members, same order."""
    knobs = knobs_for(LAYOUTS[layout])
    postmortem_active = knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start

    handwritten = build_channels(knobs=knobs, postmortem_active=postmortem_active)
    declared = team_structure.channels(teams=veyru_teams(knobs=knobs))

    assert as_comparable(declared) == as_comparable(handwritten)


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
def test_the_declaration_wires_the_same_agents(layout: str) -> None:
    """Same agents, in the same order, each reaching the same channels.

    Tool lists are compared too: veyru's engineer cannot stabilize, and a role
    that silently gained the tool would change what the scenario measures.
    """
    knobs = knobs_for(LAYOUTS[layout])
    postmortem_active = knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
    renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])

    handwritten = build_agents(
        knobs=knobs,
        postmortem_active=postmortem_active,
        channel_display_names={},
        renderer=renderer,
        default_model="m",
        default_provider="anthropic",
    )
    declared = team_structure.build_agent_configs(
        teams=veyru_teams(knobs=knobs),
        render_system_prompt=no_prompt,
        default_model="m",
        default_provider="anthropic",
        max_tokens=knobs.agent_max_tokens,
        compaction=knobs.compaction,
    )

    assert [(a.agent_id, a.role_name) for a in declared] == [
        (a.agent_id, a.role_name) for a in handwritten
    ]
    assert [tuple(a.channel_ids) for a in declared] == [tuple(a.channel_ids) for a in handwritten]
    assert [tuple(a.tool_names) for a in declared] == [tuple(a.tool_names) for a in handwritten]


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
def test_the_task_and_debrief_channels_are_the_ones_veyru_built(layout: str) -> None:
    """The engine's notion of which channel is which must match what exists.

    These two sets drive metering, noise and the phase gate, so a declaration
    naming a channel the layout never built would meter nothing.
    """
    knobs = knobs_for(LAYOUTS[layout])
    postmortem_active = knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
    teams = veyru_teams(knobs=knobs)
    built = {c.channel_id for c in build_channels(knobs=knobs, postmortem_active=postmortem_active)}

    task = frozenset(team.task.channel_id for team in teams)
    debrief = frozenset(
        team.debrief.channel_id for team in teams if isinstance(team.debrief, Debrief)
    )

    assert task, "no channel is metered in this layout"
    assert task <= built, f"task channels not built: {task - built}"
    assert debrief <= built, f"debrief channels not built: {debrief - built}"
    assert not (task & debrief), "a channel is both the task and the debrief"
