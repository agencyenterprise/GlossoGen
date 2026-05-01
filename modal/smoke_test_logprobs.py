"""Verify pydantic-ai surfaces logprobs from a self-hosted vLLM endpoint.

Reads SELF_HOSTED_BASE_URLS / SELF_HOSTED_API_KEY from the repo's ``.env``,
points pydantic-ai at the Llama 3.3 70B Modal deployment, runs a one-shot
prompt with ``openai_logprobs=True`` + ``openai_top_logprobs=5``, then walks
``result.all_messages()`` and prints the per-token logprobs payload that
pydantic-ai exposes on each ``ModelResponse.provider_details``.

Run with:

    VIRTUAL_ENV= uv run --no-sync python modal/smoke_test_logprobs.py
"""

import asyncio
import json
import os
import pathlib

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL_NAME = "meta-llama/Llama-3.3-70B-Instruct"
TOP_LOGPROBS = 5
PROMPT = "Reply in one short sentence: what color is the sky on a clear day?"


def resolve_base_url(model: str) -> str:
    raw = os.environ["SELF_HOSTED_BASE_URLS"]
    mapping: dict[str, str] = json.loads(raw)
    if model not in mapping:
        configured = ", ".join(sorted(mapping)) or "<none>"
        raise KeyError(f"Model {model!r} not in SELF_HOSTED_BASE_URLS (have: {configured})")
    return mapping[model]


async def main() -> None:
    load_dotenv(dotenv_path=REPO_ROOT / ".env")
    base_url = resolve_base_url(model=MODEL_NAME)
    api_key = os.environ["SELF_HOSTED_API_KEY"]

    provider = OpenAIProvider(base_url=base_url, api_key=api_key)
    model = OpenAIChatModel(MODEL_NAME, provider=provider)
    settings = OpenAIChatModelSettings(
        max_tokens=64,
        openai_logprobs=True,
        openai_top_logprobs=TOP_LOGPROBS,
    )
    agent: Agent[None, str] = Agent(model=model, model_settings=settings)

    print(f"endpoint={base_url}")
    print(f"model={MODEL_NAME}")
    print(f"prompt={PROMPT!r}")
    print("---")

    result = await agent.run(user_prompt=PROMPT)
    print(f"output: {result.output!r}")
    print("---")

    found_any = False
    for msg in result.all_messages():
        if not isinstance(msg, ModelResponse):
            continue
        provider_details = msg.provider_details
        if provider_details is None:
            print("ModelResponse with provider_details=None")
            continue
        logprobs = provider_details.get("logprobs")
        if logprobs is None:
            print(f"ModelResponse provider_details keys={list(provider_details)} (no 'logprobs')")
            continue
        found_any = True
        print(f"ModelResponse with {len(logprobs)} logprob entries")
        for i, entry in enumerate(logprobs[:5]):
            top = entry.get("top_logprobs") or []
            top_preview = ", ".join(f"{alt['token']!r}:{alt['logprob']:.3f}" for alt in top[:3])
            print(
                f"  [{i}] token={entry.get('token')!r} "
                f"logprob={entry.get('logprob'):.4f} "
                f"top3=[{top_preview}]"
            )
        if len(logprobs) > 5:
            print(f"  ... ({len(logprobs) - 5} more tokens)")

    print("---")
    print(f"logprobs surfaced: {found_any}")


if __name__ == "__main__":
    asyncio.run(main())
