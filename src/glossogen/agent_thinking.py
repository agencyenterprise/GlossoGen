"""The thinking level each simulation agent runs with, resolved from the ``agent_thinking`` knob.

The level is pydantic-ai's ``ThinkingLevel``, sent as ``ModelSettings.thinking``,
which pydantic-ai translates for each provider. ``None`` sends nothing, so the
model's own default applies.

Runs recorded before the knob existed sent ``openai_reasoning_effort="high"`` to
every OpenAI reasoning model and nothing to any other provider, and their
``AgentRegistered`` events carry no ``thinking`` field. Resuming or forking such a
run keeps OpenAI reasoning models at ``high`` unless the knob names a level, so
the rounds after the boundary run at the effort the rounds before it did.
"""

from collections.abc import Sequence
from typing import NamedTuple

from pydantic_ai.settings import ThinkingLevel

from glossogen.model_catalog import Provider
from glossogen.models.event import AgentRegistered, AgentSwappedMidRun
from glossogen.runners.pydantic_ai_model_factory import openai_model_reasons

# pydantic-ai sends ``thinking`` to a self-hosted endpoint as OpenAI's
# ``reasoning_effort``, which the vLLM deployments in ``modal/`` ignore.
THINKING_UNSUPPORTED_PROVIDERS: frozenset[Provider] = frozenset({Provider.SELF_HOSTED})

_LEGACY_OPENAI_REASONING_LEVEL: ThinkingLevel = "high"


def legacy_thinking_level(model: str, provider: Provider) -> ThinkingLevel | None:
    """Return the level an agent ran with before the ``agent_thinking`` knob existed."""
    if provider == Provider.OPENAI and openai_model_reasons(model=model):
        return _LEGACY_OPENAI_REASONING_LEVEL
    return None


def registration_predates_thinking(registration: AgentRegistered | AgentSwappedMidRun) -> bool:
    """Return whether this event was logged before ``thinking`` was recorded.

    Every registration and swap logged since writes the field, ``null`` included,
    so a parsed event lacks it in ``model_fields_set`` only when its line has no
    such key.
    """
    return "thinking" not in registration.model_fields_set


def recorded_thinking_level(registration: AgentRegistered) -> ThinkingLevel | None:
    """Return the level the registered agent ran with, inferring it for a legacy log."""
    if registration_predates_thinking(registration=registration):
        return legacy_thinking_level(
            model=registration.model, provider=Provider(registration.provider)
        )
    return registration.thinking


def recorded_swap_thinking_level(swap: AgentSwappedMidRun) -> ThinkingLevel | None:
    """Return the level the swapped-in agent ran with, inferring it for a legacy log."""
    if registration_predates_thinking(registration=swap):
        return legacy_thinking_level(model=swap.new_model, provider=Provider(swap.new_provider))
    return swap.thinking


class AgentThinkingPolicy(NamedTuple):
    """How one run picks each agent's thinking level.

    ``level`` is the run's ``agent_thinking`` knob. ``pins_legacy_level`` is set
    when the run resumes a log recorded before the knob existed.
    """

    level: ThinkingLevel | None
    pins_legacy_level: bool

    def for_agent(self, model: str, provider: Provider) -> ThinkingLevel | None:
        """Return the level an agent under this model and provider runs with."""
        if self.level is not None:
            return self.level
        if self.pins_legacy_level:
            return legacy_thinking_level(model=model, provider=provider)
        return None


def thinking_policy_for_run(
    level: ThinkingLevel | None,
    resumed_registrations: Sequence[AgentRegistered],
) -> AgentThinkingPolicy:
    """Build the policy for a run from its knob and the registrations it resumes from.

    A fresh run passes no registrations.
    """
    pins_legacy_level = any(
        registration_predates_thinking(registration=registration)
        for registration in resumed_registrations
    )
    return AgentThinkingPolicy(level=level, pins_legacy_level=pins_legacy_level)
