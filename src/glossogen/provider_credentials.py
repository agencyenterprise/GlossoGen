"""Validate model-provider environment requirements before a run starts.

The check covers simulation agents, scenario judges, and scheduled agent swaps.
For resumed runs it ignores swaps before ``first_round``. It validates required
environment variables, that each scenario judge names a provider a judge can run
under, the self-hosted model-to-endpoint map, and that no agent runs under a
provider that would ignore its compaction or thinking knob; providers can still
reject invalid credentials or fail to reach a configured endpoint.
"""

import os
from typing import Any, NamedTuple

from glossogen.agent_thinking import THINKING_UNSUPPORTED_PROVIDERS
from glossogen.config_overrides import ResolvedAgentModel
from glossogen.model_catalog import (
    JUDGE_PROVIDERS,
    PROVIDER_SPECS,
    SELF_HOSTED_API_KEY_VAR,
    SELF_HOSTED_BASE_URLS_VAR,
    CredentialRequirement,
    Provider,
    provider_spec,
)
from glossogen.models.agent_config import AgentRole
from glossogen.models.compaction_config import COMPACTION_PROVIDERS
from glossogen.models.model_consumer import ModelConsumer
from glossogen.runtime.scheduled_events import SwapAgent
from glossogen.scenario_protocol import SimulationScenario
from glossogen.self_hosted_config import parse_self_hosted_base_urls

ANTHROPIC_MIN_COMPACTION_TOKENS = 50_000


class UnreachableProvider(NamedTuple):
    """One reason a run cannot reach a provider, and the callers it would have served.

    ``remedy`` is the sentence shown to whoever ran the command, because the
    thing being reported is what they have to go and do.
    """

    provider: str
    caller_names: tuple[str, ...]
    remedy: str


def require_reachable_models(
    scenario_cls: type[SimulationScenario],
    scenario_config: dict[str, Any],
    agent_overrides: dict[str, ResolvedAgentModel] | None,
    default_model: str,
    default_provider: str,
    first_round: int,
) -> None:
    """Raise ValueError naming everything that would stop this run reaching a model.

    Every flow that starts a run calls this before claiming a run directory,
    because a claimed directory is the thing the check exists to prevent. The
    flows differ in what they do with the error: the CLI exits on it, and the
    MCP ``start_run`` tool, which is the only caller of ``launch_simulation``,
    reports it as a tool error. No REST route starts a run.
    """
    agents = resolve_agent_consumers(
        roles=scenario_cls.get_agent_roles(knobs=scenario_config),
        agent_overrides=agent_overrides,
        default_model=default_model,
        default_provider=default_provider,
    )
    swaps = resolve_scheduled_swap_consumers(
        scenario_cls=scenario_cls,
        scenario_config=scenario_config,
        first_round=first_round,
    )
    judges = scenario_cls.get_judge_models(knobs=scenario_config)
    require_judge_providers(judges=judges)
    unreachable = find_unreachable_providers(consumers=agents + judges + swaps)
    if unreachable:
        raise ValueError(describe_unreachable_providers(unreachable=unreachable))
    require_compaction_supported(
        scenario_cls=scenario_cls, scenario_config=scenario_config, agents=agents + swaps
    )
    require_thinking_supported(
        scenario_cls=scenario_cls, scenario_config=scenario_config, agents=agents + swaps
    )


def require_judge_providers(judges: tuple[ModelConsumer, ...]) -> None:
    """Raise ValueError naming every scenario judge under a provider no judge can run under.

    A scenario builds its judge through ``create_provider`` on the judge's first
    call, which accepts only ``JUDGE_PROVIDERS``. A knob such as ``judge_provider``
    accepts any ``Provider``, so without this check a judge under another provider
    passes the credential check and fails at its first call, after the run started.
    Checked before credentials, so the message names the provider rather than a key.
    """
    unsupported = [judge for judge in judges if judge.provider not in JUDGE_PROVIDERS]
    if not unsupported:
        return
    callers = ", ".join(f"{judge.name} ({judge.provider})" for judge in unsupported)
    supported = ", ".join(JUDGE_PROVIDERS)
    raise ValueError(
        f"{callers}: a scenario judge runs only under {supported}. "
        "Change the judge's provider to one of them."
    )


def require_compaction_supported(
    scenario_cls: type[SimulationScenario],
    scenario_config: dict[str, Any],
    agents: tuple[ModelConsumer, ...],
) -> None:
    """Validate provider support and provider-specific compaction limits.

    The runner attaches a compaction capability for the providers in
    ``COMPACTION_PROVIDERS`` only, so under any other provider the knob would
    change nothing. Anthropic ignores thresholds below 50,000 tokens.
    """
    knobs = scenario_cls.knobs_model().model_validate(scenario_config)
    if not knobs.compaction.enabled:
        return
    unsupported = [agent for agent in agents if agent.provider not in COMPACTION_PROVIDERS]
    if not unsupported:
        if (
            any(agent.provider == Provider.ANTHROPIC for agent in agents)
            and knobs.compaction.token_threshold < ANTHROPIC_MIN_COMPACTION_TOKENS
        ):
            raise ValueError(
                "compaction.token_threshold must be at least 50000 for Anthropic; "
                "lower values are not applied by the provider."
            )
        return
    callers = ", ".join(f"{agent.name} ({agent.provider})" for agent in unsupported)
    supported = ", ".join(sorted(COMPACTION_PROVIDERS))
    raise ValueError(
        f"compaction.enabled is set, but the runner compacts history only under {supported}; "
        f"it would do nothing for {callers}. Disable compaction or change their provider."
    )


def require_thinking_supported(
    scenario_cls: type[SimulationScenario],
    scenario_config: dict[str, Any],
    agents: tuple[ModelConsumer, ...],
) -> None:
    """Raise ValueError when ``agent_thinking`` is set and an agent's provider ignores it.

    Under ``THINKING_UNSUPPORTED_PROVIDERS`` the level reaches the endpoint as a
    parameter the deployment does not read, so the run would record a level its
    agents never ran at.
    """
    knobs = scenario_cls.knobs_model().model_validate(scenario_config)
    if knobs.agent_thinking is None:
        return
    unsupported = [agent for agent in agents if agent.provider in THINKING_UNSUPPORTED_PROVIDERS]
    if not unsupported:
        return
    callers = ", ".join(f"{agent.name} ({agent.provider})" for agent in unsupported)
    raise ValueError(
        f"agent_thinking is set to {knobs.agent_thinking!r}, but {callers} would ignore it. "
        "Leave agent_thinking unset for runs with a self-hosted agent."
    )


def resolve_agent_consumers(
    roles: list[AgentRole],
    agent_overrides: dict[str, ResolvedAgentModel] | None,
    default_model: str,
    default_provider: str,
) -> tuple[ModelConsumer, ...]:
    """Return the model and provider each agent will run under, overrides applied.

    Mirrors what the simulation does to the agents it builds, so the check
    covers what the run will actually call rather than what was named on the
    command line.
    """
    if agent_overrides is None:
        overrides: dict[str, ResolvedAgentModel] = {}
    else:
        overrides = agent_overrides
    resolved: list[ModelConsumer] = []
    for role in roles:
        override = overrides.get(role.agent_id)
        if override is None:
            consumer = ModelConsumer(
                name=role.agent_id, model=default_model, provider=Provider(default_provider)
            )
        else:
            consumer = ModelConsumer(
                name=role.agent_id, model=override.model, provider=override.provider
            )
        resolved.append(consumer)
    return tuple(resolved)


def resolve_scheduled_swap_consumers(
    scenario_cls: type[SimulationScenario],
    scenario_config: dict[str, Any],
    first_round: int,
) -> tuple[ModelConsumer, ...]:
    """Return the model each scheduled swap brings in, from ``first_round`` on.

    Read through the knobs model rather than off the raw config, so the entries
    are the same typed events the runtime dispatches rather than a second
    reading of their shape.

    Boundaries below ``first_round`` are skipped because the clock will not
    visit them, which is the same rule the runtime applies to a schedule a
    resumed run inherited. ``>=`` rather than ``>``: a swap at the round a
    resume opens on does fire, since the cloned log stops before the source
    dispatched it.
    """
    knobs = scenario_cls.knobs_model().model_validate(scenario_config)
    return tuple(
        ModelConsumer(
            name=f"{event.agent_id} swapped in at round {event.at_round}",
            model=event.model,
            provider=event.provider,
        )
        for event in knobs.scheduled_events
        if isinstance(event, SwapAgent) and event.at_round >= first_round
    )


def find_unreachable_providers(
    consumers: tuple[ModelConsumer, ...],
) -> tuple[UnreachableProvider, ...]:
    """Return every reason these callers would fail to reach a model."""
    callers_by_problem: dict[tuple[str, str], list[str]] = {}
    for entry in consumers:
        for remedy in _remedies_for(model=entry.model, provider=entry.provider):
            callers_by_problem.setdefault((entry.provider, remedy), []).append(entry.name)
    return tuple(
        UnreachableProvider(
            provider=provider,
            caller_names=tuple(sorted(caller_names)),
            remedy=remedy,
        )
        for (provider, remedy), caller_names in sorted(callers_by_problem.items())
    )


def describe_unreachable_providers(unreachable: tuple[UnreachableProvider, ...]) -> str:
    """Return the message naming what to do, per problem, and who it affects."""
    lines = ["This run cannot reach every model it would call."]
    for entry in unreachable:
        callers = ", ".join(entry.caller_names)
        lines.append(f"  {entry.provider} ({callers}): {entry.remedy}")
    lines.append("Commands read the nearest .env at or above the directory they run in.")
    return "\n".join(lines)


def _remedies_for(model: str, provider: Provider) -> tuple[str, ...]:
    """Return what stands between this caller and its model, as things to go and do.

    A provider's requirements come from its row in ``PROVIDER_SPECS``. A provider
    with no row, Hugging Face as a judge, has none here: its client reads its own
    token. ``self-hosted`` also needs its endpoint map to serve the model.
    """
    if provider == Provider.SELF_HOSTED:
        return _self_hosted_remedies(model=model)
    remedies: list[str] = []
    for requirement in _requirements(provider=provider):
        if _any_name_carries_a_value(names=requirement.accepted_names):
            continue
        remedies.append(f"set {' or '.join(requirement.accepted_names)}")
    return tuple(remedies)


def _self_hosted_remedies(model: str) -> tuple[str, ...]:
    """Return what a self-hosted caller is missing, endpoint map first, then key.

    The map is read rather than only checked for presence, because a model it
    does not serve fails exactly like an unset variable, and is likelier: the
    keys are exact model strings, so serving one model and asking for another is
    a typo away.
    """
    remedies: list[str] = []
    raw = os.environ.get(SELF_HOSTED_BASE_URLS_VAR, "").strip()
    if raw == "":
        remedies.append(f"set {SELF_HOSTED_BASE_URLS_VAR}")
    else:
        remedies.extend(_endpoint_map_remedies(raw=raw, model=model))
    if not _any_name_carries_a_value(names=(SELF_HOSTED_API_KEY_VAR,)):
        remedies.append(f"set {SELF_HOSTED_API_KEY_VAR}")
    return tuple(remedies)


def _endpoint_map_remedies(raw: str, model: str) -> tuple[str, ...]:
    """Return what is wrong with the endpoint map for ``model``, if anything."""
    served = _served_models(raw=raw)
    if served is None:
        return (
            f"{SELF_HOSTED_BASE_URLS_VAR} is not a JSON object mapping model names "
            "to endpoint URLs",
        )
    if not served:
        return (f"{SELF_HOSTED_BASE_URLS_VAR} lists no models",)
    if model not in served:
        return (
            f"{SELF_HOSTED_BASE_URLS_VAR} has no endpoint for {model!r} "
            f"(it serves: {', '.join(served)})",
        )
    return ()


def _served_models(raw: str) -> tuple[str, ...] | None:
    """Return the model names the endpoint map declares, or None if it is not one."""
    try:
        mapping = parse_self_hosted_base_urls(raw=raw)
    except ValueError:
        return None
    return tuple(sorted(mapping))


def _any_name_carries_a_value(names: tuple[str, ...]) -> bool:
    """Return whether any of ``names`` is set to something other than blank.

    A name that is set and empty counts as absent. `.env.example` ships every key
    with an empty value, so a copy of it that was never filled in is the likeliest
    way to arrive here, and the provider libraries reject it anyway.
    """
    return any(os.environ.get(name, "").strip() != "" for name in names)


def _requirements(provider: Provider) -> tuple[CredentialRequirement, ...]:
    spec = provider_spec(provider=provider)
    if spec is None:
        return ()
    return spec.credentials


def credential_variable_names() -> tuple[str, ...]:
    """Return every environment variable a run's reachability can depend on.

    Derived from ``PROVIDER_SPECS`` rather than restated, so a provider added there is
    covered everywhere this list is used. `scenario_conformance` hides these while it
    builds a scenario, and a name missing from that guard is a check that passes on a
    machine holding the key and fails on one that does not.
    """
    names = {
        name
        for spec in PROVIDER_SPECS
        for requirement in spec.credentials
        for name in requirement.accepted_names
    }
    return tuple(sorted(names))
