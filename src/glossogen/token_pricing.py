"""Per-model token rates, read from the ``genai-prices`` catalog, and the cost of token counts.

Used by the agent runner (simulation cost tracking), the run views, the ATIF
export, and the evaluation module (evaluator cost reporting). Prices come from the
snapshot bundled with the installed ``genai-prices`` package, so a new model or a
price change arrives by upgrading that package. Self-hosted models are priced at
zero, since their GPU time is billed elsewhere.
"""

import functools
import logging
from datetime import datetime
from decimal import Decimal
from typing import NamedTuple

from genai_prices import Usage, calc_price
from genai_prices.types import ModelInfo, TieredPrices

from glossogen.model_catalog import Provider

logger = logging.getLogger(__name__)


class TokenPricing(NamedTuple):
    """Per-million-token prices in USD for one model."""

    input_per_mtok: float
    output_per_mtok: float
    cache_read_per_mtok: float
    cache_write_per_mtok: float


# Served from hardware billed elsewhere, so their tokens cost nothing here.
_ZERO_COST_PROVIDERS: frozenset[Provider] = frozenset({Provider.SELF_HOSTED, Provider.OLLAMA})

_SELF_HOSTED_PRICING = TokenPricing(
    input_per_mtok=0.0,
    output_per_mtok=0.0,
    cache_read_per_mtok=0.0,
    cache_write_per_mtok=0.0,
)


@functools.cache
def _find_catalog_model(model: str, provider: str) -> ModelInfo | None:
    """The ``genai-prices`` entry for a model served by ``provider``, or ``None``.

    Cached because the answer for a pair never changes within a process, and the
    run listing asks once per agent of every run.
    """
    try:
        calculation = calc_price(
            usage=Usage(input_tokens=0, output_tokens=0),
            model_ref=model,
            provider_id=provider,
        )
    except LookupError:
        logger.exception(
            "genai-prices has no price for model %r under provider %r; its tokens are not costed",
            model,
            provider,
        )
        return None
    return calculation.model


def _base_rate(price: Decimal | TieredPrices | None) -> float | None:
    if price is None:
        return None
    if isinstance(price, TieredPrices):
        return float(price.base)
    return float(price)


def find_pricing(model: str, provider: str, at: datetime) -> TokenPricing | None:
    """The model's rates in effect at ``at``, or ``None`` when ``genai-prices`` does not know it.

    ``genai-prices`` dates its price changes, so passing when the tokens were spent
    prices an old run at the rates it ran under.

    A rate with long-context tiers is taken at its base tier. The tier depends on a
    single request's input size, and the usage priced here is always a sum over
    several requests, which no longer carries it. A model with no cache-read or
    cache-write rate bills those tokens as ordinary input, as ``genai-prices`` does.
    """
    if provider in _ZERO_COST_PROVIDERS:
        return _SELF_HOSTED_PRICING
    catalog_model = _find_catalog_model(model=model, provider=provider)
    if catalog_model is None:
        return None
    prices = catalog_model.get_prices(request_timestamp=at)
    input_rate = _base_rate(price=prices.input_mtok)
    if input_rate is None:
        input_rate = 0.0
    output_rate = _base_rate(price=prices.output_mtok)
    if output_rate is None:
        output_rate = 0.0
    cache_read_rate = _base_rate(price=prices.cache_read_mtok)
    if cache_read_rate is None:
        cache_read_rate = input_rate
    cache_write_rate = _base_rate(price=prices.cache_write_mtok)
    if cache_write_rate is None:
        cache_write_rate = input_rate
    return TokenPricing(
        input_per_mtok=input_rate,
        output_per_mtok=output_rate,
        cache_read_per_mtok=cache_read_rate,
        cache_write_per_mtok=cache_write_rate,
    )


def compute_token_cost_usd(
    pricing: TokenPricing,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int,
) -> float:
    """Price token counts in USD, billing cached input at the cache rates.

    ``input_tokens`` includes the cache-read and cache-write tokens (the way
    pydantic-ai and the providers report it), so those are subtracted before the
    base input rate applies.
    """
    non_cached_input = max(0, input_tokens - cache_read_tokens - cache_write_tokens)
    return (
        non_cached_input * pricing.input_per_mtok
        + output_tokens * pricing.output_per_mtok
        + cache_read_tokens * pricing.cache_read_per_mtok
        + cache_write_tokens * pricing.cache_write_per_mtok
    ) / 1_000_000
