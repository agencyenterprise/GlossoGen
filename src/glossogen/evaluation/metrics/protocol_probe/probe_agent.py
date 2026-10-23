"""Single-shot structured probe of an agent's pydantic-ai instance against a reconstructed history.

Given an agent's original ``model``/``provider``, a reconstructed message
history, and a probe prompt, ``run_structured_probe`` builds a tool-less
pydantic-ai ``Agent`` with the caller's ``output_type`` and runs one
``agent.run(...)`` call. No MCP server, no game clock, no subprocess, just one
LLM round-trip. It returns the validated structured output together with the
token usage of the call so the caller can aggregate cost per ``(model,
provider)``.

``run_protocol_probe`` is the convenience wrapper used by the protocol_probe
metric: it assembles the ``[_PROBE_INTRO, CachePoint(), probe_prompt]`` user
prompt (so providers that support prompt caching place the cache breakpoint
between the constant intro and the varying probe text) and asks for a
``ProtocolProbeOutput``. Other metrics call ``run_structured_probe`` directly
with their own ``output_type``.
"""

import logging
from collections.abc import Sequence
from typing import Generic, TypeVar

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.messages import CachePoint, ModelMessage
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RunUsage, UsageLimits

from glossogen.evaluation.metrics.protocol_probe.response_models import ProtocolProbeOutput
from glossogen.evaluation.reports.evaluation_cost import EvaluationTokenUsage
from glossogen.model_catalog import Provider
from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.runners.pydantic_ai_model_factory import (
    build_pydantic_ai_model,
    default_pydantic_ai_settings,
    layered_model_settings,
)

logger = logging.getLogger(__name__)

_PROBE_INTRO = "PROTOCOL PROBE:"

# Anthropic reasoning models (e.g. claude-opus-4-7) spend output tokens on internal
# thinking; without an explicit cap the small Anthropic default is exhausted before
# the structured-output tool call is emitted, yielding an empty ``{}`` and a missing-
# field validation error. The OpenAI branch of ``default_pydantic_ai_settings`` already
# sets a generous cap for the same reason; mirror it for the probe's Anthropic calls.
_ANTHROPIC_PROBE_MAX_TOKENS = 32768


def _probe_model_settings(
    provider: Provider, model: str, model_settings: AgentModelSettings
) -> ModelSettings:
    """Probe-call model settings: the provider defaults the agents ran with, then the
    settings the agent ran with, then an Anthropic output cap.

    The provider defaults are ``default_pydantic_ai_settings``, the same layer the
    runner puts under every agent: Anthropic prompt caching, which the probe needs
    because it asks the whole question bank over one shared history, and on OpenAI
    the reasoning summary and a 32768-token cap.

    The agent's own output cap is left out. A probe answers in structured output,
    which needs the room the provider defaults and the Anthropic cap give it.
    """
    agent_layer = model_settings.to_pydantic_ai()
    agent_layer.pop("max_tokens", None)
    probe_layer = ModelSettings()
    if provider == Provider.ANTHROPIC:
        probe_layer["max_tokens"] = _ANTHROPIC_PROBE_MAX_TOKENS
    return layered_model_settings(
        layers=(
            default_pydantic_ai_settings(provider=provider, model=model),
            agent_layer,
            probe_layer,
        )
    )


ProbeOutputT = TypeVar("ProbeOutputT", bound=BaseModel)


class StructuredProbeResult(BaseModel, Generic[ProbeOutputT]):
    """One structured probe call's validated output bundled with its token usage."""

    output: ProbeOutputT
    usage: EvaluationTokenUsage


async def run_structured_probe(
    agent_id: str,
    role_name: str,
    full_system_prompt: str,
    model: str,
    provider: Provider,
    model_settings: AgentModelSettings,
    message_history: list[ModelMessage],
    user_prompt_parts: Sequence[str | CachePoint],
    output_type: type[ProbeOutputT],
) -> StructuredProbeResult[ProbeOutputT]:
    """Run one structured probe call against the agent and return output + usage.

    Builds a fresh ``Agent`` with no tools and the caller's ``output_type`` so
    the LLM produces a validated structured response. The caller passes the
    agent's full system prompt: the ``base_prompt + communication-protocol
    suffix`` composition the runner applied at simulation time, so
    reconstruction and the new ``Agent`` construction stay consistent.
    ``model_settings`` are the ones the agent ran with, so the probe asks the same
    model at the same effort.
    """
    agent: Agent[None, ProbeOutputT] = Agent(
        model=build_pydantic_ai_model(model=model, provider=provider),
        system_prompt=full_system_prompt,
        output_type=output_type,
        model_settings=_probe_model_settings(
            provider=provider, model=model, model_settings=model_settings
        ),
    )
    logger.info(
        "Probing agent %s (%s) under model=%s provider=%s history_len=%d output=%s",
        agent_id,
        role_name,
        model,
        provider,
        len(message_history),
        output_type.__name__,
    )
    result = await agent.run(
        user_prompt=list(user_prompt_parts),
        message_history=message_history,
        usage_limits=UsageLimits(request_limit=None),
    )
    return StructuredProbeResult(
        output=result.output,
        usage=_run_usage_to_evaluation_token_usage(run_usage=result.usage),
    )


async def run_protocol_probe(
    agent_id: str,
    role_name: str,
    full_system_prompt: str,
    model: str,
    provider: Provider,
    model_settings: AgentModelSettings,
    message_history: list[ModelMessage],
    probe_prompt: str,
) -> StructuredProbeResult[ProtocolProbeOutput]:
    """Probe the agent for the ``#link`` message it would send for a hypothetical input.

    Assembles ``[_PROBE_INTRO, CachePoint(), probe_prompt]`` so replicas sharing
    the same ``system + history + _PROBE_INTRO`` prefix hit the prompt cache, and
    asks for a ``ProtocolProbeOutput`` (reasoning + message).
    """
    return await run_structured_probe(
        agent_id=agent_id,
        role_name=role_name,
        full_system_prompt=full_system_prompt,
        model=model,
        provider=provider,
        model_settings=model_settings,
        message_history=message_history,
        user_prompt_parts=[_PROBE_INTRO, CachePoint(), probe_prompt],
        output_type=ProtocolProbeOutput,
    )


def _run_usage_to_evaluation_token_usage(run_usage: RunUsage) -> EvaluationTokenUsage:
    """Project pydantic-ai's ``RunUsage`` onto the evaluation cost token model.

    ``RunUsage.input_tokens`` is the *total* prompt token count (non-cached +
    cache_read + cache_creation), which differs from the Anthropic API's
    ``input_tokens`` (after-breakpoint only). ``compute_evaluation_cost``
    expects ``EvaluationTokenUsage.input_tokens`` to be the non-cached
    portion only, so we subtract here to match.
    """
    non_cached_input = max(
        0,
        run_usage.input_tokens - run_usage.cache_read_tokens - run_usage.cache_write_tokens,
    )
    return EvaluationTokenUsage(
        input_tokens=non_cached_input,
        output_tokens=run_usage.output_tokens,
        cache_read_input_tokens=run_usage.cache_read_tokens,
        cache_creation_input_tokens=run_usage.cache_write_tokens,
    )
