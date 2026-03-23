"""Factory function for creating the appropriate LLM provider based on model name."""

from schmidt.llm.claude_provider import ClaudeProvider
from schmidt.llm.openai_provider import OpenAIProvider
from schmidt.llm.provider import LLMProvider

OPENAI_MODEL_PREFIXES = ("gpt-", "o1", "o3", "o4")


def create_provider(model: str, reasoning_effort: str | None) -> LLMProvider:
    """Return an OpenAIProvider for GPT/o-series models, ClaudeProvider otherwise."""
    if model.startswith(OPENAI_MODEL_PREFIXES):
        return OpenAIProvider(model=model, reasoning_effort=reasoning_effort)
    return ClaudeProvider(model=model)
