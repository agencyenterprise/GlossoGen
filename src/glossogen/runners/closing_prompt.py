"""Sends an agent its closing prompt once the run has completed, and returns its answer.

A scenario sets ``RunnerPrompts.closing`` to ask its agents something after the
game. The prompt goes to the agent's own pydantic-ai ``Agent`` as one more user
prompt after its live history, so the agent answers from the context it played
with. ``tool_choice`` is ``none`` for that exchange: the tools stay declared, so
a history full of tool calls is still a valid request, but the agent can only
answer in text and can no longer act in the run.
"""

import asyncio

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import RunUsage

from glossogen.runners.agent_run_retry import agent_run_retry

CLOSING_PROMPT_TIMEOUT_SECONDS = 300.0
"""The longest the closing prompt may take, retries included, before the agent goes unasked."""


async def answer_closing_prompt(
    agent: Agent[None, str],
    history: list[ModelMessage],
    prompt: str,
    usage: RunUsage,
) -> str:
    """Send ``prompt`` to ``agent`` after ``history`` and return the text it answers with.

    ``usage`` accumulates every attempt's tokens as they are spent, so the caller
    can price the exchange when it fails or times out as well.
    """
    async with asyncio.timeout(CLOSING_PROMPT_TIMEOUT_SECONDS):
        return await _answer_with_retries(agent=agent, history=history, prompt=prompt, usage=usage)


@agent_run_retry
async def _answer_with_retries(
    agent: Agent[None, str],
    history: list[ModelMessage],
    prompt: str,
    usage: RunUsage,
) -> str:
    """One attempt at the closing prompt, with no tool call allowed."""
    result = await agent.run(
        user_prompt=prompt,
        message_history=history,
        model_settings={"tool_choice": "none"},
        usage=usage,
    )
    return result.output
