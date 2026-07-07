"""Factory function for creating LLM provider instances by name."""

from glossogen.llm.claude_provider import ClaudeProvider
from glossogen.llm.huggingface_provider import HuggingFaceProvider
from glossogen.llm.openai_provider import OpenAIProvider
from glossogen.llm.provider import LLMProvider

VALID_PROVIDERS = ("anthropic", "huggingface", "openai")


def create_provider(
    provider_name: str,
    model: str,
    inference_provider: str | None,
    reasoning_effort: str | None,
) -> LLMProvider:
    """Create an LLMProvider instance for the given provider name and model.

    Raises ValueError if the provider name is not recognized.
    """
    if provider_name == "anthropic":
        return ClaudeProvider(model=model)
    if provider_name == "huggingface":
        return HuggingFaceProvider(model=model, inference_provider=inference_provider)
    if provider_name == "openai":
        return OpenAIProvider(model=model, reasoning_effort=reasoning_effort)
    raise ValueError(
        f"Unknown provider '{provider_name}'. Valid providers: {', '.join(VALID_PROVIDERS)}"
    )
