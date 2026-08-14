"""What each provider needs in the environment before a run can reach it.

A run that cannot authenticate does not fail where it is launched. The
supervisor creates one task per agent runner and awaits them only after the
game clock has finished, so a credential the environment does not carry
surfaces once the whole configured duration has elapsed: `round_count` rounds
of `max_round_duration_seconds` each, spent on a run that registered its
agents, delivered their injections and called no model. The run directory is
claimed and the JSONL written either way, so what is left behind looks like a
run that happened. Checking the environment first turns that into an error at
the command line.

The names below are the ones the provider libraries read, so a check that
passes here still leaves every failure those libraries can report, such as a
key that is set and rejected.
"""

import os
from typing import NamedTuple

from glossogen.models.agent_config import AgentRole


class CredentialRequirement(NamedTuple):
    """Environment variables that each satisfy one credential a provider reads.

    Any one of ``accepted_names`` carrying a value satisfies the requirement. A
    provider that reads two independent values declares two requirements.
    """

    accepted_names: tuple[str, ...]


class AgentProvider(NamedTuple):
    """The provider one agent will run under."""

    agent_id: str
    provider: str


class MissingCredential(NamedTuple):
    """One credential a run needs, and the agents that would have used it."""

    provider: str
    agent_ids: tuple[str, ...]
    accepted_names: tuple[str, ...]


# A provider absent from this table contributes no requirement, so one served
# locally (ollama) and one added later are both left alone rather than blocked
# by a check that does not know them.
_REQUIREMENTS: dict[str, tuple[CredentialRequirement, ...]] = {
    "anthropic": (CredentialRequirement(accepted_names=("ANTHROPIC_API_KEY",)),),
    "openai": (CredentialRequirement(accepted_names=("OPENAI_API_KEY",)),),
    "google-gla": (CredentialRequirement(accepted_names=("GOOGLE_API_KEY", "GEMINI_API_KEY")),),
    "huggingface": (CredentialRequirement(accepted_names=("HF_TOKEN",)),),
    "self-hosted": (
        CredentialRequirement(accepted_names=("SELF_HOSTED_BASE_URLS",)),
        CredentialRequirement(accepted_names=("SELF_HOSTED_API_KEY",)),
    ),
}


def resolve_agent_providers(
    roles: list[AgentRole],
    agent_overrides: dict[str, dict[str, str]] | None,
    default_provider: str,
) -> tuple[AgentProvider, ...]:
    """Return the provider each agent will run under, per-agent overrides applied.

    Mirrors what the simulation does to the agents it builds, so the check
    covers the providers the run will actually call rather than the one named
    on the command line. ``agent_overrides`` is the normalized mapping, whose
    entries always carry a provider.
    """
    if agent_overrides is None:
        overrides: dict[str, dict[str, str]] = {}
    else:
        overrides = agent_overrides
    resolved: list[AgentProvider] = []
    for role in roles:
        override = overrides.get(role.agent_id)
        if override is None:
            provider = default_provider
        else:
            provider = override["provider"]
        resolved.append(AgentProvider(agent_id=role.agent_id, provider=provider))
    return tuple(resolved)


def find_missing_credentials(
    agent_providers: tuple[AgentProvider, ...],
) -> tuple[MissingCredential, ...]:
    """Return every credential these agents need that the environment does not carry."""
    agents_by_provider: dict[str, list[str]] = {}
    for entry in agent_providers:
        agents_by_provider.setdefault(entry.provider, []).append(entry.agent_id)

    missing: list[MissingCredential] = []
    for provider in sorted(agents_by_provider):
        for requirement in _REQUIREMENTS.get(provider, ()):
            if _any_name_carries_a_value(names=requirement.accepted_names):
                continue
            missing.append(
                MissingCredential(
                    provider=provider,
                    agent_ids=tuple(sorted(agents_by_provider[provider])),
                    accepted_names=requirement.accepted_names,
                )
            )
    return tuple(missing)


def describe_missing_credentials(missing: tuple[MissingCredential, ...]) -> str:
    """Return the message naming what to set, per provider, and who needed it."""
    lines = ["This run has no credentials for every provider it would call."]
    for entry in missing:
        agents = ", ".join(entry.agent_ids)
        names = " or ".join(entry.accepted_names)
        lines.append(f"  {entry.provider} ({agents}): set {names}")
    lines.append("Commands read the nearest .env at or above the directory they run in.")
    return "\n".join(lines)


def _any_name_carries_a_value(names: tuple[str, ...]) -> bool:
    """Return whether any of ``names`` is set to something other than blank.

    A name that is set and empty counts as absent. `.env.example` ships every
    key with an empty value, so a copy of it that was never filled in is the
    likeliest way to arrive here, and the provider libraries reject it anyway.
    """
    return any(os.environ.get(name, "").strip() != "" for name in names)
