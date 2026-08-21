"""Parsing and applying a `<knob><operator><value>` condition.

The listing tests cover the two filters end to end. These cover the grammar and
the comparison rules directly, including the cases where the answer is "matches
nothing" rather than an error, since those are invisible from the outside.
"""

import pytest

from glossogen.knob_filter import (
    KnobFilterOperator,
    KnobFilterParseError,
    matches_knob_filters,
    parse_knob_filter,
    parse_knob_filters,
)

CONFIG: dict[str, object] = {
    "round_count": 15,
    "round_time_budget_seconds": 250,
    "channel_noise_level": 0.3,
    "postmortem_enabled": True,
    "judge_model": "claude-haiku-4-5-20251001",
    "noise_replacement_mode": "mask",
    "easy_round_numbers": [1, 2, 3],
    "model_overrides": {"field_observer": "opus"},
    # An optional knob the run left unset, which is what a no-swap veyru run records.
    "swap_round": None,
}


@pytest.mark.parametrize(
    ("raw", "knob", "operator", "value"),
    [
        ("round_count=15", "round_count", KnobFilterOperator.EQ, "15"),
        ("round_count!=15", "round_count", KnobFilterOperator.NE, "15"),
        ("round_count>=15", "round_count", KnobFilterOperator.GE, "15"),
        ("round_count<=15", "round_count", KnobFilterOperator.LE, "15"),
        ("round_count>15", "round_count", KnobFilterOperator.GT, "15"),
        ("round_count<15", "round_count", KnobFilterOperator.LT, "15"),
        ("  round_count  >=  15  ", "round_count", KnobFilterOperator.GE, "15"),
        ("judge_model=", "judge_model", KnobFilterOperator.EQ, ""),
    ],
)
def test_each_operator_parses(
    raw: str,
    knob: str,
    operator: KnobFilterOperator,
    value: str,
) -> None:
    """The grammar reads every operator, and trims the whitespace around the parts."""
    parsed = parse_knob_filter(raw=raw)
    assert (parsed.knob, parsed.operator, parsed.value_text) == (knob, operator, value)


@pytest.mark.parametrize(
    ("raw", "knob", "value"),
    [
        # The value carries operator characters. Splitting on the longest
        # operator anywhere would ask about a knob named "judge_model=gpt".
        ("judge_model=gpt>=5", "judge_model", "gpt>=5"),
        ("judge_model=a!=b", "judge_model", "a!=b"),
        ("judge_model=x<y", "judge_model", "x<y"),
    ],
)
def test_the_knob_name_ends_at_the_first_operator(raw: str, knob: str, value: str) -> None:
    """A value may contain an operator character, which a model name does."""
    parsed = parse_knob_filter(raw=raw)
    assert parsed.knob == knob
    assert parsed.operator is KnobFilterOperator.EQ
    assert parsed.value_text == value


@pytest.mark.parametrize("raw", [">=200", "=15", "<5"])
def test_an_operator_at_the_start_is_not_a_separator(raw: str) -> None:
    """It would leave an empty knob name, so there is no condition to apply."""
    with pytest.raises(KnobFilterParseError):
        parse_knob_filter(raw=raw)


@pytest.mark.parametrize("raw", ["roundcount15", "nonsense", ""])
def test_a_condition_with_no_operator_is_refused(raw: str) -> None:
    """Refused rather than dropped: dropping it would widen the result silently."""
    with pytest.raises(KnobFilterParseError) as caught:
        parse_knob_filter(raw=raw)
    assert "carries no operator" in str(caught.value)


def test_parsing_a_list_stops_at_the_first_bad_entry() -> None:
    """One malformed condition invalidates the set rather than being skipped."""
    with pytest.raises(KnobFilterParseError):
        parse_knob_filters(raw_filters=["round_count=15", "nonsense"])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Numbers, including a float knob and an int compared against a float.
        ("round_time_budget_seconds>=250", True),
        ("round_time_budget_seconds>250", False),
        ("round_time_budget_seconds<=250", True),
        ("round_time_budget_seconds<250", False),
        ("round_time_budget_seconds=250", True),
        ("round_time_budget_seconds!=250", False),
        ("round_count>=14.5", True),
        ("channel_noise_level<0.5", True),
        ("channel_noise_level>0.5", False),
        # A value that is not a number cannot be compared with one.
        ("round_count>=lots", False),
        # Booleans. Every spelling of each, and no ordering.
        ("postmortem_enabled=true", True),
        ("postmortem_enabled=True", True),
        ("postmortem_enabled=1", True),
        ("postmortem_enabled=yes", True),
        ("postmortem_enabled=on", True),
        ("postmortem_enabled=false", False),
        ("postmortem_enabled!=false", True),
        ("postmortem_enabled=maybe", False),
        ("postmortem_enabled>=1", False),
        ("postmortem_enabled<2", False),
        # Strings and enum-valued knobs, case-insensitive, equality only.
        ("judge_model=claude-haiku-4-5-20251001", True),
        ("judge_model=CLAUDE-HAIKU-4-5-20251001", True),
        ("judge_model=gpt-5.4", False),
        ("judge_model!=gpt-5.4", True),
        ("judge_model>=claude", False),
        ("judge_model<zzz", False),
        ("noise_replacement_mode=mask", True),
        ("noise_replacement_mode=random_letter", False),
        ("noise_replacement_mode!=random_letter", True),
        # Neither a list nor a mapping is filterable.
        ("easy_round_numbers=1", False),
        ("easy_round_numbers!=1", False),
        ("model_overrides=field_observer", False),
        # A knob the run never recorded, under both directions.
        ("no_such_knob=1", False),
        ("no_such_knob!=1", False),
        # A knob recorded as null. It answered "not set", so equality against a
        # value naming null holds and inequality against a number does too.
        ("swap_round=null", True),
        ("swap_round=NULL", True),
        # "none" and "unset" are ordinary values, so they ask about a knob whose
        # recorded value is that string. Reserving them would make a string or
        # enum knob holding one unfilterable.
        ("swap_round=none", False),
        ("swap_round=unset", False),
        ("swap_round!=null", False),
        ("swap_round!=16", True),
        ("swap_round=16", False),
        ("swap_round>=1", False),
        ("swap_round<=1", False),
        ("swap_round>0", False),
        ("swap_round<99", False),
        # The empty value asks for the empty string, not for the unset state, so
        # a knob recorded as null does not answer it.
        ("swap_round=", False),
        # A recorded value against the set-ness question.
        ("round_count=null", False),
        ("round_count!=null", True),
        ("judge_model!=null", True),
        ("postmortem_enabled!=null", True),
        ("round_count>=null", False),
    ],
)
def test_one_condition_against_a_recorded_config(raw: str, expected: bool) -> None:
    """Every comparison rule, including the ones that answer False rather than raise."""
    matched = matches_knob_filters(
        scenario_config=CONFIG,
        knob_filters=parse_knob_filters(raw_filters=[raw]),
    )
    assert matched is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("model_overrides.field_observer.model=gpt-5.4", True),
        ("model_overrides.field_observer.model!=gpt-5.4", False),
        ("model_overrides.field_observer.provider=openai", True),
        ("model_overrides.field_observer.model=claude", False),
        # A path that runs out part way is absent, not false.
        ("model_overrides.nobody.model=gpt-5.4", False),
        ("model_overrides.nobody.model!=gpt-5.4", False),
        # A path through something that is not a mapping.
        ("round_count.nested=1", False),
    ],
)
def test_a_nested_knob_is_addressed_with_dots(raw: str, expected: bool) -> None:
    """The same spelling the CSV export uses for that column.

    ``knob.model_overrides.field_observer.model`` is an export column and an
    analysis dimension, so a condition naming it has to read the same value
    rather than looking for a top-level key of that name and finding none.
    """
    config: dict[str, object] = {
        "round_count": 15,
        "model_overrides": {"field_observer": {"model": "gpt-5.4", "provider": "openai"}},
    }
    assert (
        matches_knob_filters(
            scenario_config=config,
            knob_filters=parse_knob_filters(raw_filters=[raw]),
        )
        is expected
    )


def test_a_literal_top_level_key_wins_over_the_dotted_reading() -> None:
    """A scenario is free to declare a knob whose name contains a dot."""
    config: dict[str, object] = {"a.b": "literal", "a": {"b": "nested"}}
    assert matches_knob_filters(
        scenario_config=config,
        knob_filters=parse_knob_filters(raw_filters=["a.b=literal"]),
    )


def test_the_null_token_does_not_shadow_a_literal_value() -> None:
    """Only "null" names the unset state, so other spellings stay usable."""
    config: dict[str, object] = {"mode": "none", "other": None}

    def matches(raw: str, cfg: dict[str, object]) -> bool:
        return matches_knob_filters(
            scenario_config=cfg, knob_filters=parse_knob_filters(raw_filters=[raw])
        )

    assert matches("mode=none", config)
    assert not matches("mode=null", config)
    assert matches("other=null", config)
    assert not matches("other=none", config)


def test_conditions_are_and_matched() -> None:
    """Every condition has to hold, so one failing rejects the run."""
    both_hold = ["round_count=15", "postmortem_enabled=true"]
    one_fails = ["round_count=15", "postmortem_enabled=false"]
    assert matches_knob_filters(
        scenario_config=CONFIG,
        knob_filters=parse_knob_filters(raw_filters=both_hold),
    )
    assert not matches_knob_filters(
        scenario_config=CONFIG,
        knob_filters=parse_knob_filters(raw_filters=one_fails),
    )


def test_no_conditions_matches_every_run() -> None:
    """An empty filter set is not a filter."""
    assert matches_knob_filters(scenario_config={}, knob_filters=[])


@pytest.mark.parametrize("raw", ["swap_round=null", "swap_round!=16"])
def test_a_recorded_null_is_not_the_same_as_a_missing_knob(raw: str) -> None:
    """The run that recorded null answered; the run without the key did not.

    Collapsing the two would make "runs that never swapped" indistinguishable
    from "runs predating the knob", which are different sets.
    """
    knob_filters = parse_knob_filters(raw_filters=[raw])
    assert matches_knob_filters(scenario_config={"swap_round": None}, knob_filters=knob_filters)
    assert not matches_knob_filters(scenario_config={}, knob_filters=knob_filters)


@pytest.mark.parametrize("recorded", [None, 16, "x", True, 0.5])
def test_the_two_set_questions_partition_the_runs(recorded: object) -> None:
    """``=null`` and ``!=null`` are complements, whatever the recorded value.

    This is what the "not set" control depends on: ticking it and choosing = or
    != has to split the runs recording that knob, with none counted twice and
    none dropped.
    """
    config: dict[str, object] = {"k": recorded}
    is_null = matches_knob_filters(
        scenario_config=config,
        knob_filters=parse_knob_filters(raw_filters=["k=null"]),
    )
    is_set = matches_knob_filters(
        scenario_config=config,
        knob_filters=parse_knob_filters(raw_filters=["k!=null"]),
    )
    assert is_null != is_set
