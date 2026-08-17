"""What a run needs in the environment before it can reach the models it calls.

A run that cannot reach a model does not fail where it is launched. The
supervisor creates one task per agent runner and awaits them only after the game
clock has finished, so an agent that dies on its first call surfaces once the
whole configured duration has elapsed: `round_count` rounds of
`max_round_duration_seconds` each. The run directory is claimed and the JSONL
written either way, so what is left behind looks like a run that happened, and
the process exits 0. Checking the environment first turns that into an error at
the command line.

Two things stop a caller getting to a model, and they behave identically. One is
a credential the environment does not carry. The other is `self-hosted` naming a
model that `SELF_HOSTED_BASE_URLS` does not serve, which is a spelling mistake
away at all times, since the map is keyed by the exact model string.

Agents are not the only callers. A scenario that judges its own rounds calls a
model under a provider its own knobs name, `anthropic` for every judge shipped
here whatever the agents run under. That one hides better than the rest: the
judge is built on first use, so a run whose agents authenticate starts, spends,
and reaches its first judged action before anything goes wrong.

A scheduled `swap_agent` hides better still. It names its own model and provider
and is built at a round boundary, so an unreachable one costs every round before
the swap, at full price, and then kills the agent it was meant to bring in.

Where the run starts decides which of those boundaries it will ever cross. A
resumed run inherits its source's whole schedule and opens at `first_round`, and
the clock never visits what is below that, so demanding a credential for a swap
the run has already outlived refuses it for a model nothing will call. A swap
exactly at `first_round` does fire on resume, and is checked.

The names below are the ones pydantic-ai accepts, which is narrower than what the
vendor SDKs read: `anthropic` builds a client from `ANTHROPIC_AUTH_TOKEN` alone,
and pydantic-ai refuses it, so listing that here would pass a run the platform
cannot start. A check that passes still leaves every failure those libraries can
report, such as a key that is set and rejected, or an endpoint that is listed and
down.
"""

import json
import os
from typing import Any, NamedTuple, cast

from glossogen.models.agent_config import AgentRole
from glossogen.models.model_consumer import ModelConsumer
from glossogen.runtime.scheduled_events import SwapAgent
from glossogen.scenario_protocol import SimulationScenario
from glossogen.token_pricing import SELF_HOSTED_PROVIDER

SELF_HOSTED_BASE_URLS_VAR = "SELF_HOSTED_BASE_URLS"
SELF_HOSTED_API_KEY_VAR = "SELF_HOSTED_API_KEY"


class CredentialRequirement(NamedTuple):
    """Environment variables that each satisfy one credential a provider reads.

    Any one of ``accepted_names`` carrying a value satisfies the requirement. A
    provider that reads two independent values declares two requirements.
    """

    accepted_names: tuple[str, ...]


class UnreachableProvider(NamedTuple):
    """One reason a run cannot reach a provider, and the callers it would have served.

    ``remedy`` is the sentence shown to whoever ran the command, because the
    thing being reported is what they have to go and do.
    """

    provider: str
    caller_names: tuple[str, ...]
    remedy: str


# A provider absent from this table contributes no requirement, so one served
# locally (ollama) and one added later are both left alone rather than blocked by
# a check that does not know them. `self-hosted` is handled separately: what it
# needs depends on the model, not only on the provider.
_REQUIREMENTS: dict[str, tuple[CredentialRequirement, ...]] = {
    "anthropic": (CredentialRequirement(accepted_names=("ANTHROPIC_API_KEY",)),),
    "openai": (CredentialRequirement(accepted_names=("OPENAI_API_KEY",)),),
    "google-gla": (CredentialRequirement(accepted_names=("GOOGLE_API_KEY", "GEMINI_API_KEY")),),
}


def require_reachable_models(
    scenario_cls: type[SimulationScenario],
    scenario_config: dict[str, Any],
    agent_overrides: dict[str, dict[str, str]] | None,
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
    unreachable = find_unreachable_providers(
        consumers=resolve_agent_consumers(
            roles=scenario_cls.get_agent_roles(knobs=scenario_config),
            agent_overrides=agent_overrides,
            default_model=default_model,
            default_provider=default_provider,
        )
        + scenario_cls.get_judge_models(knobs=scenario_config)
        + resolve_scheduled_swap_consumers(
            scenario_cls=scenario_cls,
            scenario_config=scenario_config,
            first_round=first_round,
        )
    )
    if unreachable:
        raise ValueError(describe_unreachable_providers(unreachable=unreachable))


def resolve_agent_consumers(
    roles: list[AgentRole],
    agent_overrides: dict[str, dict[str, str]] | None,
    default_model: str,
    default_provider: str,
) -> tuple[ModelConsumer, ...]:
    """Return the model and provider each agent will run under, overrides applied.

    Mirrors what the simulation does to the agents it builds, so the check
    covers what the run will actually call rather than what was named on the
    command line. ``agent_overrides`` is the normalized mapping, whose entries
    always carry both a model and a provider.
    """
    if agent_overrides is None:
        overrides: dict[str, dict[str, str]] = {}
    else:
        overrides = agent_overrides
    resolved: list[ModelConsumer] = []
    for role in roles:
        override = overrides.get(role.agent_id)
        if override is None:
            model = default_model
            provider = default_provider
        else:
            model = override["model"]
            provider = override["provider"]
        resolved.append(ModelConsumer(name=role.agent_id, model=model, provider=provider))
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


def _remedies_for(model: str, provider: str) -> tuple[str, ...]:
    """Return what stands between this caller and its model, as things to go and do."""
    if provider == SELF_HOSTED_PROVIDER:
        return _self_hosted_remedies(model=model)
    remedies: list[str] = []
    for requirement in _REQUIREMENTS.get(provider, ()):
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
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return tuple(sorted(str(name) for name in cast(dict[Any, Any], parsed)))


def _any_name_carries_a_value(names: tuple[str, ...]) -> bool:
    """Return whether any of ``names`` is set to something other than blank.

    A name that is set and empty counts as absent. `.env.example` ships every key
    with an empty value, so a copy of it that was never filled in is the likeliest
    way to arrive here, and the provider libraries reject it anyway.
    """
    return any(os.environ.get(name, "").strip() != "" for name in names)


def credential_variable_names() -> tuple[str, ...]:
    """Return every environment variable a run's reachability can depend on.

    Derived from the table above rather than restated, so a provider added there is
    covered everywhere this list is used. `scenario_conformance` hides these while it
    builds a scenario, and a name missing from that guard is a check that passes on a
    machine holding the key and fails on one that does not.
    """
    names = {
        name
        for requirements in _REQUIREMENTS.values()
        for requirement in requirements
        for name in requirement.accepted_names
    }
    return tuple(sorted(names | {SELF_HOSTED_BASE_URLS_VAR, SELF_HOSTED_API_KEY_VAR}))
