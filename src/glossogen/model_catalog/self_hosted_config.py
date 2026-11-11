"""Parse the model-to-endpoint map used by the self-hosted provider."""

import json
from typing import cast


def parse_self_hosted_base_urls(raw: str) -> dict[str, str]:
    """Parse ``SELF_HOSTED_BASE_URLS`` and validate every model and endpoint."""
    parsed: object = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(
            "SELF_HOSTED_BASE_URLS must be a JSON object mapping model names "
            "to non-empty endpoint URLs"
        )
    mapping = cast(dict[object, object], parsed)
    if not all(
        isinstance(name, str) and isinstance(url, str) and bool(url.strip())
        for name, url in mapping.items()
    ):
        raise ValueError(
            "SELF_HOSTED_BASE_URLS must be a JSON object mapping model names "
            "to non-empty endpoint URLs"
        )
    return cast(dict[str, str], mapping)
