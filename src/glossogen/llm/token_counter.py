"""Provider-specific token counters for measuring message length.

Each counter calls its provider's official token counting API to return
an exact count. Providers without a counting API fall back to a word-count
heuristic. The factory function selects the right implementation based on
the provider name.
"""

import logging
import os
from abc import ABC, abstractmethod

import anthropic
import cachetools
import openai

logger = logging.getLogger(__name__)


class TokenCounter(ABC):
    """Counts the number of tokens in a text string using a provider's tokenizer.

    Results are cached with an LRU eviction policy so repeated calls with the
    same text skip the external API round-trip.
    """

    def __init__(self) -> None:
        self._cache: cachetools.LRUCache[str, int] = cachetools.LRUCache(maxsize=1024)

    async def count(self, text: str) -> int:
        """Return the token count for the given text, using the cache when possible."""
        cached = self._cache.get(text)
        if cached is not None:
            return cached
        result = await self._count_impl(text=text)
        self._cache[text] = result
        return result

    @abstractmethod
    async def _count_impl(self, text: str) -> int:
        """Provider-specific token counting implementation."""
        ...


class AnthropicTokenCounter(TokenCounter):
    """Counts tokens using the Anthropic Messages count_tokens API.

    The API is free and returns the exact token count that the model's
    tokenizer produces. Requires ``ANTHROPIC_API_KEY`` in the environment.
    """

    def __init__(self, model: str) -> None:
        super().__init__()
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def _count_impl(self, text: str) -> int:
        """Count tokens via the Anthropic count_tokens endpoint."""
        try:
            response = await self._client.messages.count_tokens(
                model=self._model,
                messages=[{"role": "user", "content": text}],
            )
            return response.input_tokens
        except Exception:
            logger.exception(
                "Anthropic token count failed for model %s, falling back to word count",
                self._model,
            )
            return len(text.split())


class OpenAITokenCounter(TokenCounter):
    """Counts tokens using the OpenAI Responses input_tokens.count API.

    Returns the exact token count for the model's tokenizer. Requires
    ``OPENAI_API_KEY`` in the environment.
    """

    def __init__(self, model: str) -> None:
        super().__init__()
        api_key = os.environ.get("OPENAI_API_KEY", "")
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model

    async def _count_impl(self, text: str) -> int:
        """Count tokens via the OpenAI input_tokens.count endpoint."""
        try:
            response = await self._client.responses.input_tokens.count(
                model=self._model,
                input=text,
            )
            return response.input_tokens
        except Exception:
            logger.exception(
                "OpenAI token count failed for model %s, falling back to word count",
                self._model,
            )
            return len(text.split())


class HeuristicTokenCounter(TokenCounter):
    """Estimates tokens using word count for providers without a counting API."""

    async def _count_impl(self, text: str) -> int:
        """Approximate token count by splitting on whitespace."""
        return len(text.split())


def create_token_counter(provider: str, model: str) -> TokenCounter:
    """Create the appropriate token counter for a given provider and model.

    Returns an ``AnthropicTokenCounter`` for Anthropic, an ``OpenAITokenCounter``
    for OpenAI, or a ``HeuristicTokenCounter`` for all other providers.
    """
    if provider == "anthropic":
        return AnthropicTokenCounter(model=model)
    if provider == "openai":
        return OpenAITokenCounter(model=model)
    logger.warning(
        "No token counting API for provider %s, using word-count heuristic",
        provider,
    )
    return HeuristicTokenCounter()
