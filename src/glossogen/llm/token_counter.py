"""Token counters for measuring message length, backed by pydantic-ai models.

The factory builds the agent's pydantic-ai ``Model`` the same way the runner does
and counts through its ``count_tokens``, which calls the provider's counting
endpoint. A provider whose model does not implement ``count_tokens`` gets a
word-count heuristic instead.
"""

import logging
from abc import ABC, abstractmethod

import cachetools
from pydantic_ai.messages import ModelRequest
from pydantic_ai.models import Model, ModelRequestParameters, infer_model

from glossogen.model_catalog import Provider
from glossogen.runners.pydantic_ai_model_factory import build_pydantic_ai_model

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


class ModelTokenCounter(TokenCounter):
    """Counts tokens with a pydantic-ai model's ``count_tokens``.

    The text is counted as a single user message. When the call fails, the error
    is logged and the word count is returned, so a run keeps going.
    """

    def __init__(self, model: Model) -> None:
        super().__init__()
        self._model = model

    async def _count_impl(self, text: str) -> int:
        """Count tokens through the model's provider counting endpoint."""
        try:
            usage = await self._model.count_tokens(
                messages=[ModelRequest.user_text_prompt(user_prompt=text)],
                model_settings=None,
                model_request_parameters=ModelRequestParameters(),
            )
            return usage.input_tokens
        except Exception:
            logger.exception(
                "Token count failed for %s model %s, falling back to word count",
                self._model.system,
                self._model.model_name,
            )
            return word_count(text=text)


class HeuristicTokenCounter(TokenCounter):
    """Estimates tokens using word count for providers without a counting API."""

    async def _count_impl(self, text: str) -> int:
        """Approximate token count by splitting on whitespace."""
        return word_count(text=text)


def word_count(text: str) -> int:
    """Return the number of whitespace-separated words in ``text``."""
    return len(text.split())


def implements_token_counting(model: Model) -> bool:
    """Return whether ``model``'s class overrides pydantic-ai's ``Model.count_tokens``.

    The base implementation raises ``NotImplementedError``.
    """
    return type(model).count_tokens is not Model.count_tokens


def create_token_counter(provider: Provider, model: str) -> TokenCounter:
    """Create the token counter for an agent running ``model`` under ``provider``.

    Returns a ``ModelTokenCounter`` when the provider's pydantic-ai model implements
    ``count_tokens``, and a ``HeuristicTokenCounter`` when it does not or when the
    model cannot be built (a missing API key or self-hosted URL, for instance).
    """
    try:
        pydantic_ai_model = infer_model(
            model=build_pydantic_ai_model(model=model, provider=provider),
        )
    except Exception:
        logger.exception(
            "Could not build the %s model %s for token counting, using word-count heuristic",
            provider,
            model,
        )
        return HeuristicTokenCounter()
    if not implements_token_counting(model=pydantic_ai_model):
        logger.warning(
            "No token counting for provider %s, using word-count heuristic",
            provider,
        )
        return HeuristicTokenCounter()
    return ModelTokenCounter(model=pydantic_ai_model)
