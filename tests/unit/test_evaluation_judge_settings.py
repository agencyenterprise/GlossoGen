"""``evaluate --judge-settings`` and how the settings are recorded in the report."""

import pytest
from pydantic import ValidationError

from glossogen.evaluation.evaluation_judge_settings import parse_judge_settings
from glossogen.evaluation.reports.evaluation_cost import (
    EvaluationCost,
    EvaluationTokenUsage,
    compute_evaluation_cost,
)
from glossogen.evaluation.reports.evaluation_report import merge_evaluation_costs
from glossogen.models.agent_model_settings import JudgeModelSettings

USAGE = EvaluationTokenUsage(
    input_tokens=1_000,
    output_tokens=200,
    cache_read_input_tokens=0,
    cache_creation_input_tokens=0,
)


def cost_under(settings: JudgeModelSettings | None) -> EvaluationCost:
    """One invocation's cost under the canonical judge and ``settings``."""
    return compute_evaluation_cost(
        usage=USAGE,
        model="claude-haiku-4-5-20251001",
        provider_name="anthropic",
        model_settings=settings,
    )


def test_no_flag_sends_no_settings() -> None:
    """The provider decides the output cap; on Anthropic that is the model's maximum."""
    settings = parse_judge_settings(raw=None)

    assert settings == JudgeModelSettings()
    assert settings.to_pydantic_ai() == {}


def test_a_flag_without_a_cap_sends_none() -> None:
    settings = parse_judge_settings(raw='{"thinking": "low"}')

    assert settings.max_tokens is None
    assert settings.to_pydantic_ai() == {"thinking": "low"}


def test_a_flag_naming_a_cap_sets_it() -> None:
    assert parse_judge_settings(raw='{"max_tokens": 65536}').max_tokens == 65536


@pytest.mark.parametrize("raw", ['["max_tokens"]', '"low"', "not json"])
def test_a_flag_that_is_not_a_json_object_is_refused(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_judge_settings(raw=raw)


def test_a_setting_nobody_defined_is_refused() -> None:
    with pytest.raises(ValidationError):
        parse_judge_settings(raw='{"max_token": 100}')


def test_invocations_under_the_same_settings_add_up() -> None:
    settings = parse_judge_settings(raw=None)

    merged = merge_evaluation_costs(existing=cost_under(settings), new=cost_under(settings))

    assert merged.usage.input_tokens == 2 * USAGE.input_tokens
    assert merged.model_settings == settings


def test_changing_the_settings_restarts_the_running_total() -> None:
    """The report's cost describes one judge, and a judge is its model plus its settings."""
    before = cost_under(parse_judge_settings(raw=None))
    after = cost_under(parse_judge_settings(raw='{"max_tokens": 65536}'))

    merged = merge_evaluation_costs(existing=before, new=after)

    assert merged == after


def test_a_report_written_before_settings_were_recorded_still_loads() -> None:
    legacy = EvaluationCost.model_validate(
        {
            "usage": USAGE.model_dump(),
            "estimated_cost_usd": 0.01,
            "model": "claude-haiku-4-5-20251001",
            "provider_name": "anthropic",
        }
    )

    assert legacy.model_settings is None
