"""The provider table, row by row: each provider is reachable, priced and checked at launch.

Every row of ``PROVIDER_SPECS`` is held to what the rest of the platform reads
from it.
"""

from datetime import UTC, datetime

import pytest
from pydantic_ai.models import infer_model

from glossogen.model_catalog import (
    JUDGE_PROVIDERS,
    PROVIDER_SPECS,
    SELF_HOSTED_API_KEY_VAR,
    SELF_HOSTED_BASE_URLS_VAR,
    SIMULATION_PROVIDERS,
    Provider,
    ProviderSpec,
    list_models,
)
from glossogen.models.model_consumer import ModelConsumer
from glossogen.provider_credentials import credential_variable_names, find_unreachable_providers
from glossogen.run_export.model_weight_class import model_class_of
from glossogen.runners.pydantic_ai_model_factory import build_pydantic_ai_model
from glossogen.server.runs.models import AgentModelSummary
from glossogen.server.scenarios.router import list_scenarios
from glossogen.token_pricing import find_pricing

SELF_HOSTED_MODEL = "my-fine-tune"
UNLISTED_MODELS: dict[Provider, str] = {
    Provider.SELF_HOSTED: SELF_HOSTED_MODEL,
    Provider.OLLAMA: "llama3",
    Provider.GOOGLE_GLA: "gemini-2.5-flash",
}


def model_for(provider: Provider) -> str:
    """A model each provider serves: a picker entry where there is one."""
    unlisted = UNLISTED_MODELS.get(provider)
    if unlisted is not None:
        return unlisted
    return next(model for model, listed in list_models() if listed == provider)


def set_credentials(spec: ProviderSpec, monkeypatch: pytest.MonkeyPatch) -> None:
    """Set exactly the variables the row names, with values the provider accepts."""
    for requirement in spec.credentials:
        name = requirement.accepted_names[0]
        value = "test-key"
        if name == SELF_HOSTED_BASE_URLS_VAR:
            value = f'{{"{SELF_HOSTED_MODEL}": "http://localhost:8000/v1"}}'
        elif name == "OLLAMA_BASE_URL":
            value = "http://localhost:11434/v1"
        monkeypatch.setenv(name, value)


@pytest.fixture(autouse=True)
def no_provider_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test with none of the variables a provider reads."""
    for name in credential_variable_names():
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("spec", PROVIDER_SPECS, ids=lambda spec: spec.provider.value)
def test_each_provider_builds_its_model_from_the_variables_its_row_names(
    spec: ProviderSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row naming the wrong variable fails here: pydantic-ai would find no key."""
    set_credentials(spec=spec, monkeypatch=monkeypatch)

    built = build_pydantic_ai_model(model=model_for(provider=spec.provider), provider=spec.provider)

    if isinstance(built, str):
        infer_model(built)


@pytest.mark.parametrize(
    "model, provider",
    [entry for entry in list_models() if entry[1] in SIMULATION_PROVIDERS],
    ids=lambda value: str(value),
)
def test_every_model_the_pickers_offer_is_priced(model: str, provider: Provider) -> None:
    assert find_pricing(model=model, provider=provider, at=datetime.now(tz=UTC)) is not None


async def test_the_evaluation_picker_offers_only_models_a_judge_runs_under() -> None:
    """The run picker offers every model; an evaluation refuses a non-judge provider."""
    response = await list_scenarios()

    offered = {(entry.model_prefix, entry.provider) for entry in response.models}
    judge_offered = {(entry.model_prefix, entry.provider) for entry in response.judge_models}
    assert judge_offered
    assert {provider for _, provider in judge_offered} <= set(JUDGE_PROVIDERS)
    assert ("grok-4.6", Provider.XAI) in offered
    assert ("grok-4.6", Provider.XAI) not in judge_offered


def test_the_launch_check_names_a_new_providers_missing_key() -> None:
    unreachable = find_unreachable_providers(
        consumers=(ModelConsumer(name="field_observer", model="grok-4.6", provider=Provider.XAI),)
    )

    assert [entry.remedy for entry in unreachable] == ["set XAI_API_KEY"]


def test_every_providers_key_is_hidden_while_a_scenario_is_validated() -> None:
    """``scenario_conformance`` hides these names; a row's key missing here would leak in."""
    names = credential_variable_names()
    for spec in PROVIDER_SPECS:
        for requirement in spec.credentials:
            assert set(requirement.accepted_names) <= set(names)
    assert SELF_HOSTED_API_KEY_VAR in names


def summary(provider: Provider) -> AgentModelSummary:
    return AgentModelSummary(
        agent_id=provider.value,
        role_name="Seat",
        model="m",
        provider=provider.value,
        harness="pydantic-ai",
    )


def test_a_runs_weight_class_follows_the_models_its_providers_serve() -> None:
    assert model_class_of(agent_models=[summary(provider=Provider.GROQ)]) == "open"
    assert model_class_of(agent_models=[summary(provider=Provider.XAI)]) == "closed"
    assert (
        model_class_of(
            agent_models=[summary(provider=Provider.DEEPSEEK), summary(provider=Provider.XAI)]
        )
        == "mixed"
    )
    assert model_class_of(agent_models=[summary(provider=Provider.OPENROUTER)]) == ""
