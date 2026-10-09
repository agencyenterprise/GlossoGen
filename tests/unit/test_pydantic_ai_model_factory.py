"""Provider mappings passed to Pydantic AI."""

import pytest
from pydantic import ValidationError
from pydantic_ai.models import infer_model
from pydantic_ai.models.google import GoogleModel

from glossogen.model_catalog import Provider
from glossogen.runners.pydantic_ai_model_factory import (
    build_pydantic_ai_model,
    resolve_self_hosted_base_url,
)
from glossogen.scenarios.base_knobs import BaseKnobs


def test_google_gla_uses_pydantic_ais_google_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    model_name = build_pydantic_ai_model(
        model="gemini-2.5-flash",
        provider=Provider.GOOGLE_GLA,
    )
    assert model_name == "google:gemini-2.5-flash"
    assert isinstance(infer_model(model_name), GoogleModel)


@pytest.mark.parametrize(
    "mapping",
    ["[]", '{"model": null}', '{"model": ""}'],
)
def test_self_hosted_endpoint_map_must_contain_non_empty_urls(
    monkeypatch: pytest.MonkeyPatch,
    mapping: str,
) -> None:
    monkeypatch.setenv("SELF_HOSTED_BASE_URLS", mapping)
    with pytest.raises(ValueError, match="non-empty endpoint URLs"):
        resolve_self_hosted_base_url(model="model")


def test_agent_output_token_limit_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        BaseKnobs(
            round_count=1,
            max_round_duration_seconds=1,
            model_overrides={},
            agent_max_tokens=0,
        )
