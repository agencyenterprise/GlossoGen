"""Single-shot probe of an agent's pydantic-ai instance against a reconstructed history.

Given an agent's original ``model``/``provider``, a reconstructed message
history, and a probe prompt, builds a tool-less pydantic-ai ``Agent`` with
``output_type=ProtocolProbeOutput`` and runs one ``agent.run(...)`` call.
No MCP server, no game clock, no subprocess — just one LLM round-trip.
"""

import logging

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import UsageLimits

from schmidt.evaluation.protocol_probe_response import ProtocolProbeOutput
from schmidt.runners.pydantic_ai_model_factory import (
    build_pydantic_ai_model,
    default_pydantic_ai_settings,
)

logger = logging.getLogger(__name__)


async def run_protocol_probe(
    agent_id: str,
    role_name: str,
    full_system_prompt: str,
    model: str,
    provider: str,
    message_history: list[ModelMessage],
    probe_prompt: str,
) -> ProtocolProbeOutput:
    """Run one structured probe call against the agent and return the validated output.

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
        user_prompt=probe_prompt,
        message_history=message_history,
        usage_limits=UsageLimits(request_limit=None),
    )
    return result.output
