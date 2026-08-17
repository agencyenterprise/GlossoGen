"""Check a scenario against the contract, without launching it.

`SimulationScenario` is an ABC, so Python already enforces that the abstract
methods exist. What it cannot enforce is that they agree with each other: an
agent may list a channel nobody created, a preset may have drifted from the
knobs model it is validated against, `get_agent_roles` may name a different set
of agents than `get_agents` builds. Each of those surfaces as a confusing
failure minutes into a paid run, or as a metric that silently scores nothing.

These live here rather than in the test suite because a scenario can ship from
any distribution, and the tests do not. `glossogen validate <name-or-directory>`
runs them against whatever it resolves, installed or not; the repository's own
conformance suite runs them over the built-ins.

Every check is a function taking a built scenario and returning the reason it
failed, or None. That shape is what lets one run report every problem rather
than the first.
"""

import ast
import importlib
import json
import logging
import os
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any, NamedTuple

from pydantic_core import PydanticUndefined

from glossogen.evaluation.metric_core.metric_registry import available_metrics
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import core_event_types, parser_for
from glossogen.models.event_base import EventBase
from glossogen.provider_credentials import credential_variable_names
from glossogen.runtime.mcp_tools import BASE_TOOL_NAMES
from glossogen.scenario_protocol import SimulationScenario
from glossogen.server.runs.primary_channel_resolution import resolve_primary_channel_ids

logger = logging.getLogger(__name__)

CHECK_MODEL = "claude-sonnet-4-6"
CHECK_PROVIDER = "anthropic"

# Read from `provider_credentials` rather than restated, so a provider added to the
# launch check is hidden here too. HF is added on top: the launch check declares no
# requirement for it, and a scenario reaching for it at construction would still
# make this a live credential check.
_CREDENTIAL_VARIABLES = (*credential_variable_names(), "HF_TOKEN")


class BuiltScenario(NamedTuple):
    """One scenario built from one of its presets, and what it declares."""

    name: str
    preset: str
    prepared: dict[str, Any]
    scenario: SimulationScenario
    agents: list[AgentConfig]


class CheckOutcome(NamedTuple):
    """What one check said about one preset."""

    check: str
    preset: str
    passed: bool
    detail: str


def check_scenario(scenario_cls: type[SimulationScenario]) -> list[CheckOutcome]:
    """Run every check against every preset the scenario ships.

    A scenario shipping no preset fails on that alone: it cannot be launched
    without hand-writing knobs, and the frontend's picker has nothing to offer.
    """
    presets = scenario_cls.knobs_preset_names()
    if not presets:
        return [
            CheckOutcome(
                check="ships a preset",
                preset="",
                passed=False,
                detail="no knobs_*.json in the scenario package, so it cannot be launched",
            )
        ]

    outcomes: list[CheckOutcome] = [_roles_resolve_without_knobs(scenario_cls=scenario_cls)]
    for preset in presets:
        outcomes.extend(_check_preset(scenario_cls=scenario_cls, preset=preset))
    return outcomes


def failures(outcomes: list[CheckOutcome]) -> list[CheckOutcome]:
    """Return only what failed, which is what a caller reports and exits on."""
    return [outcome for outcome in outcomes if not outcome.passed]


def _check_preset(scenario_cls: type[SimulationScenario], preset: str) -> list[CheckOutcome]:
    """Build one preset and run the per-preset checks against it.

    Building is itself the first check: `prepare_config` then
    `create_from_config` is the exact pair `glossogen run` calls at preflight,
    so a preset that fails here fails at launch too. Nothing else can run when
    it does, so this returns early.
    """
    try:
        with _no_provider_credentials():
            config = scenario_cls.load_knobs_preset(preset_name=preset)
            prepared = scenario_cls.prepare_config(config=dict(config))
            scenario = scenario_cls.create_from_config(config=dict(prepared))
            agents = scenario.get_agents(default_model=CHECK_MODEL, default_provider=CHECK_PROVIDER)
    except Exception as exc:
        logger.exception("Building %s from preset %s failed", scenario_cls.name(), preset)
        return [
            CheckOutcome(
                check="the preset builds the scenario",
                preset=preset,
                passed=False,
                detail=f"{type(exc).__name__}: {exc}",
            )
        ]

    built = BuiltScenario(
        name=scenario_cls.name(),
        preset=preset,
        prepared=prepared,
        scenario=scenario,
        agents=agents,
    )
    outcomes: list[CheckOutcome] = [
        CheckOutcome(check="the preset builds the scenario", preset=preset, passed=True, detail="")
    ]
    for name, check in _CHECKS:
        outcomes.append(_run_one(name=name, check=check, built=built))
    return outcomes


def _run_one(
    name: str,
    check: Callable[[BuiltScenario], str | None],
    built: BuiltScenario,
) -> CheckOutcome:
    """Run one check, turning a raise into a failure rather than a crash."""
    try:
        detail = check(built)
    except Exception as exc:
        logger.exception("Check %r raised on %s:%s", name, built.name, built.preset)
        detail = f"raised {type(exc).__name__}: {exc}"
    if detail is None:
        return CheckOutcome(check=name, preset=built.preset, passed=True, detail="")
    return CheckOutcome(check=name, preset=built.preset, passed=False, detail=detail)


@contextmanager
def _no_provider_credentials() -> Generator[None]:
    """Hide provider keys for the duration of the block.

    Describing a scenario must not require a key for anybody's model. Scenarios
    hold an LLM judge, and building one eagerly makes construction a live
    credential check, which reaches much further than the judge:
    `validate_run_config` builds a scenario to preflight a config, `evaluate`
    and the resume flows build one to read its config back, and the run-detail
    API builds one to ask which channels it scores.
    """
    saved = {name: os.environ.pop(name, None) for name in _CREDENTIAL_VARIABLES}
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is not None:
                os.environ[name] = value


def _roles_resolve_without_knobs(scenario_cls: type[SimulationScenario]) -> CheckOutcome:
    """The API asks for roles before the user has configured anything.

    `get_agent_roles(knobs=None)` has to answer with the scenario's baseline
    layout rather than raising on a missing role-determining flag.
    """
    check = "roles resolve without knobs"
    try:
        roles = scenario_cls.get_agent_roles(knobs=None)
    except Exception as exc:
        logger.exception("get_agent_roles(knobs=None) raised for %s", scenario_cls.name())
        return CheckOutcome(
            check=check, preset="", passed=False, detail=f"raised {type(exc).__name__}: {exc}"
        )
    if not roles:
        return CheckOutcome(check=check, preset="", passed=False, detail="returned no roles")
    ids = [role.agent_id for role in roles]
    if len(set(ids)) != len(ids):
        return CheckOutcome(check=check, preset="", passed=False, detail=f"duplicate ids: {ids}")
    return CheckOutcome(check=check, preset="", passed=True, detail="")


def _name_matches_the_package(built: BuiltScenario) -> str | None:
    """`name()` derives from the package directory, and runs are stored under it.

    Run directories are `runs/<name>/<timestamp>`, and evaluation looks the
    scenario back up by that string. A mismatch writes runs nobody can re-open.
    """
    if type(built.scenario).name() != built.name:
        return f"name() is {type(built.scenario).name()!r}, registered as {built.name!r}"
    return None


def _agents_are_distinct_and_specified(built: BuiltScenario) -> str | None:
    """Duplicate ids would collide in the MCP session map and the event log."""
    if not built.agents:
        return "a scenario with no agents cannot run"
    ids = [agent.agent_id for agent in built.agents]
    if len(set(ids)) != len(ids):
        return f"duplicate agent ids: {sorted(ids)}"
    for agent in built.agents:
        if not agent.system_prompt.strip():
            return f"{agent.agent_id} has an empty system prompt"
        if agent.max_tokens <= 0:
            return f"{agent.agent_id} has max_tokens={agent.max_tokens}"
    return None


def _agents_claim_channels_that_exist(built: BuiltScenario) -> str | None:
    """A channel id no channel answers to fails every send for the whole run.

    Weaker than "the agent is a member of it": membership can be granted later,
    which is how a scenario builds an agent that arrives mid-run.
    """
    channel_ids = {channel.channel_id for channel in built.scenario.get_channels()}
    for agent in built.agents:
        unknown = set(agent.channel_ids) - channel_ids
        if unknown:
            return f"{agent.agent_id} lists channels that do not exist: {sorted(unknown)}"
    return None


def _members_declare_their_channel(built: BuiltScenario) -> str | None:
    """This direction has no deferred case, so it holds from the start.

    A member nobody built has messages delivered to a session that never
    connects. A member who does not declare the channel gets no mention of it in
    their system prompt, so they can post there but will not know to.
    """
    declared = {agent.agent_id: set(agent.channel_ids) for agent in built.agents}
    for channel in built.scenario.get_channels():
        for agent_id in channel.member_agent_ids:
            if agent_id not in declared:
                return f"channel {channel.channel_id} lists an agent nobody built: {agent_id}"
            if channel.channel_id not in declared[agent_id]:
                return f"{agent_id} is a member of {channel.channel_id} but does not declare it"
    return None


def _channel_ids_are_distinct(built: BuiltScenario) -> str | None:
    """The router keys channels by id, so a duplicate silently loses one."""
    ids = [channel.channel_id for channel in built.scenario.get_channels()]
    if len(set(ids)) != len(ids):
        return f"duplicate channel ids: {sorted(ids)}"
    return None


def _primary_channels_exist(built: BuiltScenario) -> str | None:
    """Every throughput and language metric reads these and nothing else.

    Naming a channel that does not exist scores an empty transcript, and the
    metric reports a number rather than an error.
    """
    channel_ids = {channel.channel_id for channel in built.scenario.get_channels()}
    unknown = [
        primary.channel_id
        for primary in built.scenario.get_primary_channels()
        if primary.channel_id not in channel_ids
    ]
    if unknown:
        return f"primary channels that do not exist: {sorted(unknown)}"
    return None


def _declared_tools_exist(built: BuiltScenario) -> str | None:
    """`tool_names` is the per-agent authorization list the MCP guard enforces.

    A name here that no tool answers to is an agent authorized for nothing,
    which shows up as a refused call rather than a startup error.
    """
    available = BASE_TOOL_NAMES | {tool.name for tool in built.scenario.get_mcp_tools()}
    for agent in built.agents:
        unknown = set(agent.tool_names) - available
        if unknown:
            return f"{agent.agent_id} is authorized for unknown tools: {sorted(unknown)}"
    return None


def _tool_names_are_distinct(built: BuiltScenario) -> str | None:
    """FastMCP registers by name; a repeat silently shadows the earlier tool."""
    names = [tool.name for tool in built.scenario.get_mcp_tools()]
    if len(set(names)) != len(names):
        return f"duplicate tool names: {sorted(names)}"
    shadowed = set(names) & BASE_TOOL_NAMES
    if shadowed:
        return f"scenario tools shadow base communication tools: {sorted(shadowed)}"
    return None


def _roles_match_built_agents(built: BuiltScenario) -> str | None:
    """`get_agent_roles` runs without an instance, so it can drift from `get_agents`.

    The API calls it to render the per-agent model override form before a run
    exists. If it names a different set, the form offers overrides for agents
    that will never be built, and preflight rejects them as unknown ids.
    """
    role_ids = {
        role.agent_id for role in type(built.scenario).get_agent_roles(knobs=built.prepared)
    }
    agent_ids = {agent.agent_id for agent in built.agents}
    if role_ids != agent_ids:
        return f"roles {sorted(role_ids)} but builds {sorted(agent_ids)}"
    return None


def _knobs_schema_is_serializable(built: BuiltScenario) -> str | None:
    """MCP clients and the frontend both fetch this as JSON."""
    schema = type(built.scenario).knobs_json_schema()
    json.dumps(schema)
    if schema.get("type") != "object":
        return f"knobs schema is {schema.get('type')!r}, not an object"
    return None


def _config_round_trips(built: BuiltScenario) -> str | None:
    """What gets written to the JSONL has to rebuild the same scenario.

    `evaluate`, fork and every resume flow reconstruct from the dumped config in
    `SimulationStarted`. A knob that dumps in a shape its own model rejects makes
    a finished run unevaluatable, and only after the run has been paid for.
    """
    dumped = built.scenario.get_scenario_config()
    json.dumps(dumped, default=str)
    rebuilt = type(built.scenario).create_from_config(config=dict(dumped))
    if rebuilt.get_scenario_config() != dumped:
        return "rebuilding from the dumped config produced different knobs"
    return None


def _description_says_something(built: BuiltScenario) -> str | None:
    """It is what the run detail page shows to explain what was simulated."""
    if len(built.scenario.scenario_description().strip()) <= 50:
        return "the description is shorter than 50 characters"
    return None


def _injections_render_for_every_round(built: BuiltScenario) -> str | None:
    """Every round's injection renders, not only the first.

    Rendering happens after the run directory is claimed and agents have
    connected, so a broken template costs a launch to discover, and a template
    reached only from round 12 costs the eleven rounds before it as well. Round one
    is not representative: scenarios swap templates per round, index a case list by
    round number, and bring an agent in partway through.

    What this cannot reach is the branch that needs a previous round's outcome.
    Nothing has been played here, so every round renders with none, and a template
    reading one renders its empty case. That branch belongs to the round loop, and
    `run_rounds(round_count=2)` in `glossogen.testing` covers it.
    """
    for round_number in range(1, built.scenario.get_knobs().round_count + 1):
        for agent in built.agents:
            try:
                built.scenario.get_injection(round_number=round_number, agent_id=agent.agent_id)
            except Exception as exc:
                logger.exception(
                    "Rendering the round %d injection for %s failed",
                    round_number,
                    agent.agent_id,
                )
                return (
                    f"round {round_number} for {agent.agent_id} raised "
                    f"{type(exc).__name__}: {exc}"
                )
    return None


def _postmortem_injections_render(built: BuiltScenario) -> str | None:
    """A postmortem template only renders once a round has ended.

    That is minutes into a paid run, and later than round-one injections, so it
    is the template most likely to reach production unrendered. Scenarios
    without a postmortem return None here and pass trivially.

    Every round, for the same reason as the injections above.
    """
    for round_number in range(1, built.scenario.get_knobs().round_count + 1):
        for agent in built.agents:
            try:
                built.scenario.get_postmortem_injection(
                    round_number=round_number, agent_id=agent.agent_id
                )
            except Exception as exc:
                logger.exception(
                    "Rendering the round %d postmortem injection for %s failed",
                    round_number,
                    agent.agent_id,
                )
                return (
                    f"round {round_number} for {agent.agent_id} raised "
                    f"{type(exc).__name__}: {exc}"
                )
    return None


def _postmortem_duration_matches_the_phase(built: BuiltScenario) -> str | None:
    """A closed postmortem must report zero duration, not its configured length."""
    knobs = built.scenario.get_knobs()
    is_open = knobs.postmortem_enabled and not built.scenario.get_world().is_postmortem_disabled
    duration = built.scenario.get_max_postmortem_duration_seconds()
    if (duration > 0.0) != is_open:
        return f"postmortem open={is_open} but duration={duration}"
    return None


def _blocked_channels_are_the_declared_ones(built: BuiltScenario) -> str | None:
    """One declaration feeds the history filter, the phase, and the disabled set.

    A replaced agent must not read the predecessor's postmortem traffic, which
    is where agents discuss the protocol out of band.
    """
    scenario_cls = type(built.scenario)
    declared = scenario_cls.postmortem_channel_ids
    if scenario_cls.get_replace_agent_blocked_tool_call_channels() != declared:
        return "blocked history channels differ from the declared postmortem channels"
    return None


def _api_agrees_on_primary_channels(built: BuiltScenario) -> str | None:
    """The run-detail response is the frontend's only source for this.

    The round timeline filters messages to these channels, so a disagreement
    renders an empty timeline under a channel name the scenario never used.
    """
    resolved = resolve_primary_channel_ids(
        scenario_name=built.name, scenario_config=built.scenario.get_scenario_config()
    )
    declared = [entry.channel_id for entry in built.scenario.get_primary_channels()]
    if resolved != declared:
        return f"the API resolves {resolved} but the scenario declares {declared}"
    return None


def _advertised_metrics_are_registered(built: BuiltScenario) -> str | None:
    """`--metrics` is validated against this list, and the UI offers it.

    Compared against every runnable metric rather than only the built-in ones,
    because an installed metric package legitimately adds to both sides.
    """
    unknown = set(type(built.scenario).get_available_metric_names()) - set(available_metrics())
    if unknown:
        return f"advertises metrics that are not registered: {sorted(unknown)}"
    return None


def _display_names_fall_back_to_ids(built: BuiltScenario) -> str | None:
    """Rendering must never produce an empty label, named or not."""
    for agent in built.agents:
        if not built.scenario.get_agent_display_name(agent_id=agent.agent_id).strip():
            return f"{agent.agent_id} has an empty display name"
        if not built.scenario.get_agent_display_name_at_round(
            agent_id=agent.agent_id, round_number=1
        ).strip():
            return f"{agent.agent_id} has an empty display name at round 1"
    for channel in built.scenario.get_channels():
        for agent_id in channel.member_agent_ids:
            if not built.scenario.get_channel_display_name(
                channel_id=channel.channel_id, agent_id=agent_id
            ).strip():
                return f"channel {channel.channel_id} has an empty display name for {agent_id}"
    return None


def _events_module_name(built: BuiltScenario) -> str | None:
    """Return the dotted name of this scenario's ``events`` module, or None.

    Asked of the scenario module's own import spec rather than assembled by
    trimming a dot off ``__module__``. ``parent`` is the value Python resolves a
    relative import against, so it answers correctly both for the usual class in a
    ``scenario`` submodule and for one defined in the package's ``__init__``, where
    trimming a dot names the package above and reaches for somebody else's events.

    None when the class is in a top-level module belonging to no package, which has
    no sibling ``events`` to find.
    """
    spec = importlib.import_module(type(built.scenario).__module__).__spec__
    if spec is None or not spec.parent:
        return None
    return f"{spec.parent}.events"


def _scenario_event_types(built: BuiltScenario) -> tuple[type[EventBase], ...]:
    """Return the event types this scenario's ``events`` module defines.

    Read from the module rather than from ``EventBase.__subclasses__``, which
    holds every scenario's at once and cannot say whose is whose. Importing is
    also the point: discovery tolerates a broken external ``events`` module so a
    third-party plug-in cannot stop the platform reading unrelated logs, which
    means its author is never told, and a path-loaded scenario's module has not
    been imported at all.
    """
    name = _events_module_name(built=built)
    if name is None:
        return ()
    module = importlib.import_module(name)
    return tuple(
        attribute
        for attribute in vars(module).values()
        if isinstance(attribute, type)
        and issubclass(attribute, EventBase)
        and attribute is not EventBase
        and attribute.__module__ == module.__name__
    )


def _events_module_is_importable(built: BuiltScenario) -> str | None:
    """A scenario with no ``events`` module passes; one that raises does not.

    Discovery logs and skips an external module that raises, so nothing else ever
    reports it and the scenario runs with its own events missing from the parser.
    """
    name = _events_module_name(built=built)
    if name is None:
        return None
    try:
        importlib.import_module(name)
    except ModuleNotFoundError:
        return None
    except Exception as exc:
        logger.exception("Importing %s failed", name)
        return f"{name} raised {type(exc).__name__}: {exc}"
    return None


def _events_declare_a_literal_discriminator(built: BuiltScenario) -> str | None:
    """``event_type`` is what the parser dispatches on, and it has to be fixed.

    Checked before the parser is built, so the reason reads as the field being
    wrong rather than as pydantic refusing a union.
    """
    for event_type in _scenario_event_types(built=built):
        field = event_type.model_fields.get("event_type")
        if field is None:
            return f"{event_type.__name__} declares no event_type"
        if field.default is PydanticUndefined or not isinstance(field.default, str):
            return (
                f"{event_type.__name__} has no fixed event_type; declare it as "
                'Literal["..."] with that value as its default'
            )
    return None


def _events_do_not_collide_with_the_platform(built: BuiltScenario) -> str | None:
    """A repeated discriminator shadows one side of the parser.

    Whichever loses, the run that wrote it reads back afterwards as the other
    thing, and nothing about writing it looked wrong.
    """
    core = {
        str(event_type.model_fields["event_type"].default): event_type.__name__
        for event_type in core_event_types()
    }
    seen: dict[str, str] = {}
    for event_type in _scenario_event_types(built=built):
        discriminator = str(event_type.model_fields["event_type"].default)
        if discriminator in core:
            return (
                f"{event_type.__name__} uses event_type {discriminator!r}, which the "
                f"platform's {core[discriminator]} already answers to"
            )
        if discriminator in seen:
            return (
                f"{event_type.__name__} and {seen[discriminator]} both use event_type "
                f"{discriminator!r}"
            )
        seen[discriminator] = event_type.__name__
    return None


def _events_parse_alongside_the_platform(built: BuiltScenario) -> str | None:
    """The run has to read back, and the parser is what reads it.

    Building the union is the check: pydantic refuses one it cannot dispatch. A
    union built here rather than the module-level parser, which was built while
    ``models.event`` was importing and so cannot see a scenario loaded from a path
    afterwards.
    """
    own = _scenario_event_types(built=built)
    if not own:
        return None
    parser_for(event_types=(*core_event_types(), *own))
    for event_type in own:
        json.dumps(event_type.model_json_schema())
    return None


def _events_import_only_the_base_module(built: BuiltScenario) -> str | None:
    """``events.py`` importing ``models.event`` deadlocks discovery.

    That module builds its union by importing every scenario's ``events`` while it
    is itself mid-import, so an ``events`` module that imports back from it closes
    the cycle. Read from the source rather than by importing, because by the time
    an import would fail the platform has already failed to start.
    """
    events_file = built.scenario.scenario_package_files() / "events.py"
    if not events_file.is_file():
        return None
    tree = ast.parse(events_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "glossogen.models.event":
            return (
                f"events.py imports from glossogen.models.event at line {node.lineno}; "
                "import glossogen.models.event_base instead, or discovery deadlocks"
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "glossogen.models.event":
                    return (
                        f"events.py imports glossogen.models.event at line {node.lineno}; "
                        "import glossogen.models.event_base instead"
                    )
    return None


def _judge_models_are_shaped(built: BuiltScenario) -> str | None:
    """Whatever the hook says is believed, so it has to be readable.

    Deliberately not compared against the knobs. That comparison was written, and
    removed again, when a scenario that scores its rounds without an LLM turned out
    to declare the knobs anyway and the check refused runs for a key it would never
    spend. What the hook reports is the scenario's to decide; this only checks the
    launch check can read it.
    """
    for entry in type(built.scenario).get_judge_models(knobs=built.prepared):
        if not entry.model.strip() or not entry.provider.strip():
            return f"the judge named {entry.name!r} has an empty model or provider"
        if not entry.name.strip():
            return f"a judge on {entry.model!r} has no name, so a refusal cannot say which"
    return None


def _probe_config_points_at_files_that_exist(built: BuiltScenario) -> str | None:
    """A probe bank that is not there makes the whole probe family score nothing.

    Every one of those metrics reads this config, and a missing file is reported
    per metric as having nothing to measure, which is indistinguishable from a run
    that had nothing to measure.
    """
    config = built.scenario.get_protocol_probe_config()
    if config is None:
        return None
    if not config.questions_path.is_file():
        return f"the probe question bank is missing: {config.questions_path}"
    try:
        json.loads(config.questions_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return f"the probe question bank is not valid JSON: {exc}"
    if not config.prompts_dir.is_dir():
        return f"the probe prompts directory is missing: {config.prompts_dir}"
    for role, template in config.role_templates.items():
        if not (config.prompts_dir / template).is_file():
            return f"the probe template for {role!r} is missing: {template}"
    return None


def _explanation_config_points_at_templates_that_exist(built: BuiltScenario) -> str | None:
    """Same failure as the probe config, one metric further along."""
    config = built.scenario.get_protocol_explanation_config()
    if config is None:
        return None
    if not config.prompts_dir.is_dir():
        return f"the explanation prompts directory is missing: {config.prompts_dir}"
    for role, template in config.role_templates.items():
        if not (config.prompts_dir / template).is_file():
            return f"the explanation template for {role!r} is missing: {template}"
    return None


def _communication_hooks_answer_in_shape(built: BuiltScenario) -> str | None:
    """Both opt out by their return value, so both are called to see they can be.

    Called with no events, which is the shape every caller starts from and the one
    a scenario that indexes rather than iterates gets wrong.
    """
    built.scenario.build_communication_rounds(events=[])
    built.scenario.detect_protocol_boundary_window(events=[], agent_configs=[])
    return None


_CHECKS: tuple[tuple[str, Callable[[BuiltScenario], str | None]], ...] = (
    ("name matches the package directory", _name_matches_the_package),
    ("agents are distinct and specified", _agents_are_distinct_and_specified),
    ("agents claim channels that exist", _agents_claim_channels_that_exist),
    ("channel members declare their channel", _members_declare_their_channel),
    ("channel ids are distinct", _channel_ids_are_distinct),
    ("primary channels exist", _primary_channels_exist),
    ("declared tools exist", _declared_tools_exist),
    ("tool names are distinct", _tool_names_are_distinct),
    ("roles match the agents built", _roles_match_built_agents),
    ("the knobs schema is serializable", _knobs_schema_is_serializable),
    ("the config round-trips", _config_round_trips),
    ("the description says something", _description_says_something),
    ("injections render for every round", _injections_render_for_every_round),
    ("postmortem injections render for every round", _postmortem_injections_render),
    ("postmortem duration matches the phase", _postmortem_duration_matches_the_phase),
    ("blocked channels are the declared ones", _blocked_channels_are_the_declared_ones),
    ("the API agrees on primary channels", _api_agrees_on_primary_channels),
    ("advertised metrics are registered", _advertised_metrics_are_registered),
    ("display names fall back to ids", _display_names_fall_back_to_ids),
    ("the events module imports", _events_module_is_importable),
    ("events declare a literal event_type", _events_declare_a_literal_discriminator),
    ("events do not collide with the platform's", _events_do_not_collide_with_the_platform),
    ("events parse alongside the platform's", _events_parse_alongside_the_platform),
    ("events.py imports only the event base", _events_import_only_the_base_module),
    ("declared judge models are readable", _judge_models_are_shaped),
    ("the probe config points at files that exist", _probe_config_points_at_files_that_exist),
    (
        "the explanation config points at templates that exist",
        _explanation_config_points_at_templates_that_exist,
    ),
    ("the communication hooks answer in shape", _communication_hooks_answer_in_shape),
)
