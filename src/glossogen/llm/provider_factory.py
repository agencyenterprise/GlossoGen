"""Factory function for creating LLM provider instances by name."""

from glossogen.llm.claude_provider import ClaudeProvider
from glossogen.llm.huggingface_provider import HuggingFaceProvider
from glossogen.llm.openai_provider import OpenAIProvider
from glossogen.llm.provider import LLMProvider
from glossogen.model_catalog import JUDGE_PROVIDERS, Provider


def create_provider(
    provider_name: str,
    model: str,
    inference_provider: str | None,
    reasoning_effort: str | None,
) -> LLMProvider:
    """Create an LLMProvider instance for the given provider name and model.

    Raises ValueError if the provider name is not recognized.
    """
    if provider_name == Provider.ANTHROPIC:
        return ClaudeProvider(model=model)
    if provider_name == Provider.HUGGINGFACE:
        return HuggingFaceProvider(model=model, inference_provider=inference_provider)
    if provider_name == Provider.OPENAI:
        return OpenAIProvider(model=model, reasoning_effort=reasoning_effort)
    raise ValueError(
        f"Unknown provider '{provider_name}'. Judge providers: {', '.join(JUDGE_PROVIDERS)}"
    )
