"""Every registered scenario, against every knobs preset it ships.

`SimulationScenario` is an ABC, so Python already enforces that the abstract
methods exist. What it cannot enforce is that they agree with each other: an
agent may list a channel nobody created, a preset may have drifted from the
knobs model it is validated against, `get_agent_roles` may name a different set
of agents than `get_agents` builds. Each of those surfaces as a confusing
failure minutes into a run, or as a metric that silently scores nothing.

These are parametrized over the registry rather than written per scenario, so a
new scenario is covered the moment it is registered, and a new rule applies to
every existing one.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from glossogen.evaluation.metric_core.metric_registry import GENERIC_METRIC_REGISTRY
from glossogen.models.agent_config import AgentConfig
from glossogen.runtime.mcp_tools import BASE_TOOL_NAMES
from glossogen.scenario_loader import get_scenario_class
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenario_registry import SCENARIO_REGISTRY

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_PROVIDER = "anthropic"

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "src" / "glossogen" / "scenarios"


def preset_paths() -> list[tuple[str, Path]]:
    """Return every (scenario_name, knobs preset) pair shipped in the package.

    These files are what the docs tell people to pass to `--config`, and what
    the frontend offers in its preset picker, so a preset that no longer
    validates is a broken published entry point.
    """
    pairs: list[tuple[str, Path]] = []
    for name in sorted(SCENARIO_REGISTRY):
        pairs.extend((name, path) for path in sorted((SCENARIOS_DIR / name).glob("knobs*.json")))
    return pairs


PRESETS = preset_paths()
PRESET_IDS = [f"{name}:{path.stem}" for name, path in PRESETS]


@pytest.fixture(params=PRESETS, ids=PRESET_IDS)
def built(request: pytest.FixtureRequest) -> tuple[str, dict[str, Any], SimulationScenario]:
    """Build one scenario from one of its presets, the way the CLI does.

    `prepare_config` then `create_from_config` is the exact pair `glossogen run`
    calls at preflight, so a preset that fails here fails at launch too.
    """
    name: str
    path: Path
    name, path = request.param
    scenario_cls = get_scenario_class(name=name)
    config: dict[str, Any] = json.loads(path.read_text())
    prepared = scenario_cls.prepare_config(config=dict(config))
    return name, prepared, scenario_cls.create_from_config(config=dict(prepared))


def agents_of(scenario: SimulationScenario) -> list[AgentConfig]:
    """Build the scenario's agents on the default model."""
    return scenario.get_agents(default_model=DEFAULT_MODEL, default_provider=DEFAULT_PROVIDER)


def test_every_scenario_ships_at_least_one_preset() -> None:
    """A scenario with no preset cannot be launched without hand-writing knobs."""
    with_presets = {name for name, _ in PRESETS}
    assert with_presets == set(SCENARIO_REGISTRY)


def test_the_registry_key_is_the_package_directory(
    built: tuple[str, dict[str, Any], SimulationScenario],
) -> None:
    """`name()` derives from the module path, so the two cannot drift.

    Run directories are `runs/<name>/<timestamp>`, and evaluation looks the
    scenario back up by that string. A mismatch writes runs nobody can re-open.
    """
    name, _, scenario = built
    assert scenario.name() == name


def test_agents_are_distinct_and_fully_specified(
    built: tuple[str, dict[str, Any], SimulationScenario],
) -> None:
    """Duplicate ids would collide in the MCP session map and the event log."""
    _, _, scenario = built
    agents = agents_of(scenario)

    assert agents, "a scenario with no agents cannot run"
    ids = [agent.agent_id for agent in agents]
    assert len(ids) == len(set(ids))
    for agent in agents:
        assert agent.system_prompt.strip(), f"{agent.agent_id} has an empty system prompt"
        assert agent.model == DEFAULT_MODEL
        assert agent.provider == DEFAULT_PROVIDER
        assert agent.max_tokens > 0


def test_agents_only_claim_channels_that_exist(
    built: tuple[str, dict[str, Any], SimulationScenario],
) -> None:
    """A channel id no channel answers to fails every send for the whole run.

    Note this is weaker than "the agent is a member of it". Membership can be
    granted later: veyru's intern preset builds an intern that declares `link`
    and is added to it at the takeover round. Declared-but-not-yet-a-member is
    a legitimate state; declared-but-nonexistent is not.
    """
    _, _, scenario = built
    channel_ids = {channel.channel_id for channel in scenario.get_channels()}
    for agent in agents_of(scenario):
        unknown = set(agent.channel_ids) - channel_ids
        assert not unknown, f"{agent.agent_id} lists channels that do not exist: {sorted(unknown)}"


def test_channel_members_are_agents_that_declare_the_channel(
    built: tuple[str, dict[str, Any], SimulationScenario],
) -> None:
    """This direction has no deferred case, so it holds from the start.

    A member nobody built has messages delivered to a session that never
    connects. A member who does not declare the channel gets no mention of it
    in their system prompt, so they can post there but will not know to.
    """
    _, _, scenario = built
    declared = {agent.agent_id: set(agent.channel_ids) for agent in agents_of(scenario)}
    for channel in scenario.get_channels():
        for agent_id in channel.member_agent_ids:
            assert (
                agent_id in declared
            ), f"channel {channel.channel_id} lists an agent that does not exist: {agent_id}"
            assert (
                channel.channel_id in declared[agent_id]
            ), f"{agent_id} is a member of {channel.channel_id} but does not declare it"


def test_channel_ids_are_distinct(built: tuple[str, dict[str, Any], SimulationScenario]) -> None:
    """The router keys channels by id, so a duplicate silently loses one."""
    _, _, scenario = built
    ids = [channel.channel_id for channel in scenario.get_channels()]
    assert len(ids) == len(set(ids))


def test_primary_channels_exist(built: tuple[str, dict[str, Any], SimulationScenario]) -> None:
    """Every throughput and language metric reads these and nothing else.

    Naming a channel that does not exist scores an empty transcript, and the
    metric reports a number rather than an error.
    """
    _, _, scenario = built
    channel_ids = {channel.channel_id for channel in scenario.get_channels()}
    for primary in scenario.get_primary_channels():
        assert primary.channel_id in channel_ids


def test_declared_tools_are_tools_that_exist(
    built: tuple[str, dict[str, Any], SimulationScenario],
) -> None:
    """`tool_names` is the per-agent authorization list the MCP guard enforces.

    A name here that no tool answers to is an agent authorized for nothing,
    which shows up as a refused call rather than a startup error.
    """
    _, _, scenario = built
    available = BASE_TOOL_NAMES | {tool.name for tool in scenario.get_mcp_tools()}
    for agent in agents_of(scenario):
        unknown = set(agent.tool_names) - available
        assert not unknown, f"{agent.agent_id} is authorized for unknown tools: {sorted(unknown)}"


def test_scenario_tool_names_are_distinct(
    built: tuple[str, dict[str, Any], SimulationScenario],
) -> None:
    """FastMCP registers by name; a repeat silently shadows the earlier tool."""
    _, _, scenario = built
    names = [tool.name for tool in scenario.get_mcp_tools()]
    assert len(names) == len(set(names))
    assert not (set(names) & BASE_TOOL_NAMES), "a scenario tool shadows a base communication tool"


def test_roles_match_the_agents_that_get_built(
    built: tuple[str, dict[str, Any], SimulationScenario],
) -> None:
    """`get_agent_roles` runs without an instance, so it can drift from `get_agents`.

    The API calls it to render the per-agent model override form before a run
    exists. If it names a different set, the form offers overrides for agents
    that will never be built, and preflight rejects them as unknown ids.
    """
    _, prepared, scenario = built
    scenario_cls = type(scenario)
    role_ids = {role.agent_id for role in scenario_cls.get_agent_roles(knobs=prepared)}
    assert role_ids == {agent.agent_id for agent in agents_of(scenario)}


def test_roles_resolve_without_any_knobs(
    built: tuple[str, dict[str, Any], SimulationScenario],
) -> None:
    """The API asks for roles before the user has configured anything.

    `get_agent_roles(knobs=None)` has to answer with the scenario's baseline
    layout rather than raising on a missing role-determining flag.
    """
    _, _, scenario = built
    roles = type(scenario).get_agent_roles(knobs=None)
    assert roles
    assert len({role.agent_id for role in roles}) == len(roles)


def test_the_knobs_schema_is_serializable(
    built: tuple[str, dict[str, Any], SimulationScenario],
) -> None:
    """MCP clients and the frontend both fetch this as JSON."""
    _, _, scenario = built
    schema = type(scenario).knobs_json_schema()
    json.dumps(schema)
    assert schema["type"] == "object"


def test_the_config_round_trips_through_its_own_dump(
    built: tuple[str, dict[str, Any], SimulationScenario],
) -> None:
    """What gets written to the JSONL has to rebuild the same scenario.

    `evaluate`, fork and every resume flow reconstruct from the dumped config
    in `SimulationStarted`. A knob that dumps in a shape its own model rejects
    makes a finished run unevaluatable, and only after the run has been paid for.
    """
    _, _, scenario = built
    dumped = scenario.get_scenario_config()
    json.dumps(dumped, default=str)
    rebuilt = type(scenario).create_from_config(config=dict(dumped))
    assert rebuilt.get_scenario_config() == dumped


def test_the_description_says_something(
    built: tuple[str, dict[str, Any], SimulationScenario],
) -> None:
    """It is what the run detail page shows to explain what was simulated."""
    _, _, scenario = built
    assert len(scenario.scenario_description().strip()) > 50


def test_round_one_injections_render(
    built: tuple[str, dict[str, Any], SimulationScenario],
) -> None:
    """The first injection is the first thing every agent reads.

    Rendering happens after the run directory is claimed and agents have
    connected, so a broken template costs a launch to discover.
    """
    _, _, scenario = built
    for agent in agents_of(scenario):
        scenario.get_injection(round_number=1, agent_id=agent.agent_id)


def test_advertised_metrics_are_registered(
    built: tuple[str, dict[str, Any], SimulationScenario],
) -> None:
    """`--metrics` is validated against this list, and the UI offers it."""
    _, _, scenario = built
    unknown = set(type(scenario).get_available_metric_names()) - set(GENERIC_METRIC_REGISTRY)
    assert not unknown, f"advertises metrics that are not registered: {sorted(unknown)}"


def test_display_names_fall_back_to_ids(
    built: tuple[str, dict[str, Any], SimulationScenario],
) -> None:
    """Rendering must never produce an empty label, named or not."""
    _, _, scenario = built
    for agent in agents_of(scenario):
        assert scenario.get_agent_display_name(agent_id=agent.agent_id).strip()
        assert scenario.get_agent_display_name_at_round(
            agent_id=agent.agent_id, round_number=1
        ).strip()
    for channel in scenario.get_channels():
        for agent_id in channel.member_agent_ids:
            assert scenario.get_channel_display_name(
                channel_id=channel.channel_id, agent_id=agent_id
            ).strip()


def test_unknown_scenario_names_are_rejected() -> None:
    """The error carries the valid names, since it is usually a typo."""
    with pytest.raises(ValueError) as raised:
        get_scenario_class(name="veyroo")
    assert "veyru" in str(raised.value)
