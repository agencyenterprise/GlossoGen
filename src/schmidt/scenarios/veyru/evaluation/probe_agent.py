"""Single-shot probe of an agent's pydantic-ai instance against a reconstructed history.

Given an agent's original ``model``/``provider``, a reconstructed message
history, and a probe prompt, builds a tool-less pydantic-ai ``Agent`` with
``output_type=ProtocolProbeOutput`` and runs one ``agent.run(...)`` call.
No MCP server, no game clock, no subprocess — just one LLM round-trip.
The function returns the structured output together with the token usage
of the call so the metric can aggregate cost per ``(model, provider)``.

The user prompt is built as ``[_PROBE_INTRO, CachePoint(), probe_prompt]``
so that providers supporting prompt caching place the cache breakpoint
between the constant intro and the varying probe text. With every probe
call against the same agent sharing the same ``system + history +
_PROBE_INTRO`` prefix, replicas across all 28 questions hit the cache
instead of paying full input tokens each call.
"""

import logging

from pydantic_ai import Agent
from pydantic_ai.messages import CachePoint, ModelMessage
from pydantic_ai.usage import RunUsage, UsageLimits

from schmidt.evaluation.evaluation_cost import EvaluationTokenUsage
from schmidt.evaluation.protocol_probe_response import ProtocolProbeCallResult, ProtocolProbeOutput
from schmidt.runners.pydantic_ai_model_factory import (
    build_pydantic_ai_model,
    default_pydantic_ai_settings,
)

logger = logging.getLogger(__name__)

_PROBE_INTRO = "PROTOCOL PROBE:"


async def run_protocol_probe(
    agent_id: str,
    role_name: str,
    full_system_prompt: str,
    model: str,
    provider: str,
    message_history: list[ModelMessage],
    probe_prompt: str,
) -> ProtocolProbeCallResult:
    """Run one structured probe call against the agent and return output + usage.

    Builds a fresh ``Agent`` with no tools and ``output_type=ProtocolProbeOutput``
    so the LLM produces both ``reasoning`` and ``message`` in one structured
    response. The caller passes the agent's full system prompt — the
    ``base_prompt + communication-protocol suffix`` composition the runner
    applied at simulation time — so reconstruction and the new ``Agent``
    construction stay consistent.
    """
    agent: Agent[None, ProtocolProbeOutput] = Agent(
        model=build_pydantic_ai_model(model=model, provider=provider),
        system_prompt=full_system_prompt,
        output_type=ProtocolProbeOutput,
        model_settings=default_pydantic_ai_settings(provider=provider),
    )
    logger.info(
        "Probing agent %s (%s) under model=%s provider=%s history_len=%d",
        agent_id,
        role_name,
        model,
        provider,
        len(message_history),
    )
    result = await agent.run(
        user_prompt=[_PROBE_INTRO, CachePoint(), probe_prompt],
        message_history=message_history,
        usage_limits=UsageLimits(request_limit=None),
    )
    return ProtocolProbeCallResult(
        output=result.output,
        usage=_run_usage_to_evaluation_token_usage(run_usage=result.usage()),
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
