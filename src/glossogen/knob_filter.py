"""Filtering runs by the values in their recorded ``scenario_config``.

A filter is written as one string, ``<knob><operator><value>``, so a whole set
of them travels as repeated query parameters and as a JSON array of strings in
an export body, without either shape needing a nested object.
``time_budget_seconds>=200`` and ``postmortem_enabled=true`` are both filters.

A nested knob is addressed with dots, the way the CSV export names its column:
``model_overrides.field_observer.model=gpt-5.4``.

A knob a run recorded as null is filterable. ``swap_round=null`` selects the runs
that never swapped and ``swap_round!=null`` the ones that did, so the two
partition the runs recording that knob. ``swap_round!=16`` includes a run that
never swapped, because not swapping at all is not swapping at 16. A knob the run
never recorded at all is different, and matches nothing.

The knob name ends at the **first** operator in the string, and the longest
operator starting there wins. A value may therefore contain an operator
character, which a model name does: ``judge_model=gpt>=5`` filters ``judge_model``
for the value ``gpt>=5``.

It sits at the package root because three layers share it: the listing that
answers the runs page, the export request model that validates a selection, and
the resolver the CLI reaches with no server in front. Holding it under any one
of those would make the other two import across a boundary their own docstrings
disclaim.

Comparison is typed from the run's own recorded value rather than from the
scenario's knobs schema. The listing already holds the config it is filtering,
and reading the type off it means this module never imports a scenario class,
which keeps the schema out of the request path and lets a run recorded against
an older schema still answer.
"""

import logging
from enum import Enum
from typing import Any, NamedTuple, cast

logger = logging.getLogger(__name__)


class KnobFilterOperator(str, Enum):
    """The comparisons a knob filter can express."""

    EQ = "="
    NE = "!="
    GE = ">="
    LE = "<="
    GT = ">"
    LT = "<"


# Ordered so that, among the operators starting at the same index, the longest
# is seen first: ">=" is never read as ">" followed by a value of "=200".
_OPERATORS_BY_LENGTH = sorted(KnobFilterOperator, key=lambda op: -len(op.value))

_TRUE_TEXT = frozenset({"true", "1", "yes", "on"})
_FALSE_TEXT = frozenset({"false", "0", "no", "off"})

# What a filter writes to mean "this knob is not set". One spelling, because
# each one shadows a literal value a string or enum knob could hold: with
# "none" reserved, `mode=none` could never ask about a mode called none. The
# empty value is not among them either, since `judge_model=` asks for the empty
# string, which for a string knob is a different question from being unset.
_NULL_VALUE_TEXT = "null"

_ORDERING_OPERATORS = frozenset(
    {
        KnobFilterOperator.GE,
        KnobFilterOperator.LE,
        KnobFilterOperator.GT,
        KnobFilterOperator.LT,
    }
)


class KnobFilter(NamedTuple):
    """One parsed ``<knob><operator><value>`` condition.

    ``value_text`` stays as written. It is coerced per run, against the type of
    that run's own recorded value.
    """

    knob: str
    operator: KnobFilterOperator
    value_text: str


class KnobFilterParseError(ValueError):
    """Raised for a filter string carrying no operator, or an empty knob name."""


def _find_separator(raw: str) -> tuple[int, KnobFilterOperator] | None:
    """Locate the operator that separates the knob name from the value.

    The earliest operator wins, and among those starting at that index the
    longest one does. Scanning for the longest operator anywhere instead would
    let an operator character inside the value take over: ``judge_model=gpt>=5``
    would split on ``>=`` and ask about a knob named ``judge_model=gpt``.

    An operator at index 0 is still the separator. Skipping it and taking the
    next one would read ``>=200`` as a knob named ``>`` compared against
    ``200``, which parses cleanly and then matches nothing.
    """
    best: tuple[int, KnobFilterOperator] | None = None
    for operator in _OPERATORS_BY_LENGTH:
        index = raw.find(operator.value)
        if index < 0:
            continue
        if best is None or index < best[0]:
            best = (index, operator)
    return best


def parse_knob_filter(raw: str) -> KnobFilter:
    """Parse one ``<knob><operator><value>`` string.

    Raises :class:`KnobFilterParseError` when no operator appears, or when the
    knob name is empty. An empty value is allowed: it matches a knob whose
    recorded value is the empty string.
    """
    found = _find_separator(raw=raw)
    if found is None:
        raise KnobFilterParseError(
            f"Knob filter {raw!r} carries no operator. Expected <knob><operator><value>, "
            f"with the operator one of {', '.join(op.value for op in KnobFilterOperator)}."
        )
    index, operator = found
    knob = raw[:index].strip()
    if not knob:
        raise KnobFilterParseError(
            f"Knob filter {raw!r} names no knob before its {operator.value!r} operator. "
            f"Expected <knob><operator><value>."
        )
    return KnobFilter(
        knob=knob,
        operator=operator,
        value_text=raw[index + len(operator.value) :].strip(),
    )


def parse_knob_filters(raw_filters: list[str]) -> list[KnobFilter]:
    """Parse every filter string, preserving order."""
    return [parse_knob_filter(raw=raw) for raw in raw_filters]


def knob_filter_problem(raw_filters: list[str]) -> str | None:
    """Why these strings are not all conditions, or None when they are.

    The non-raising half of the pair, for a caller that reports the problem
    itself. The CLI is one: catching the exception there would oblige it to log a
    stack trace for what is a mistyped flag.
    """
    for raw in raw_filters:
        try:
            parse_knob_filter(raw=raw)
        except KnobFilterParseError as exc:
            return str(exc)
    return None


def _coerce_to_bool(text: str) -> bool | None:
    """Read a boolean from a filter's value text, or None when it names neither."""
    lowered = text.strip().lower()
    if lowered in _TRUE_TEXT:
        return True
    if lowered in _FALSE_TEXT:
        return False
    return None


def _coerce_to_float(text: str) -> float | None:
    """Read a number from a filter's value text, or None when it is not one."""
    try:
        return float(text)
    except ValueError:
        return None


def _compare(left: Any, right: Any, operator: KnobFilterOperator) -> bool:
    """Apply an operator to two values already coerced to a comparable pair."""
    if operator is KnobFilterOperator.EQ:
        return bool(left == right)
    if operator is KnobFilterOperator.NE:
        return bool(left != right)
    if operator is KnobFilterOperator.GE:
        return bool(left >= right)
    if operator is KnobFilterOperator.LE:
        return bool(left <= right)
    if operator is KnobFilterOperator.GT:
        return bool(left > right)
    return bool(left < right)


def _matches_bool(recorded: bool, knob_filter: KnobFilter) -> bool:
    """Compare a boolean knob. Ordering operators do not apply to one."""
    if knob_filter.operator in _ORDERING_OPERATORS:
        return False
    wanted = _coerce_to_bool(text=knob_filter.value_text)
    if wanted is None:
        return False
    return _compare(left=recorded, right=wanted, operator=knob_filter.operator)


def _matches_number(recorded: float, knob_filter: KnobFilter) -> bool:
    """Compare a numeric knob."""
    wanted = _coerce_to_float(text=knob_filter.value_text)
    if wanted is None:
        return False
    return _compare(left=recorded, right=wanted, operator=knob_filter.operator)


def _names_null(value_text: str) -> bool:
    """Whether a condition's value names the unset state rather than a value."""
    return value_text.strip().casefold() == _NULL_VALUE_TEXT


def _matches_set_question(recorded: Any, knob_filter: KnobFilter) -> bool:
    """Answer a condition whose value names null, which asks only about set-ness.

    Handled before the type dispatch, because the question is about the absence
    of a value rather than about one: a run recording ``16`` has to answer
    ``swap_round!=null`` with yes, and the numeric comparison cannot, since
    "null" is not a number.
    """
    if knob_filter.operator in _ORDERING_OPERATORS:
        return False
    if knob_filter.operator is KnobFilterOperator.EQ:
        return recorded is None
    return recorded is not None


def _matches_recorded_null(knob_filter: KnobFilter) -> bool:
    """Compare a null-recorded knob against a condition naming a concrete value.

    A recorded null is an answer, not the absence of one: an optional knob left
    unset says the run did not swap, or ran with no budget cap. So it is not
    equal to any concrete value, it is unequal to every one of them (a run that
    never swapped did not swap at round 16), and no ordering holds, since null
    sits nowhere on the number line.
    """
    if knob_filter.operator in _ORDERING_OPERATORS:
        return False
    return knob_filter.operator is KnobFilterOperator.NE


def _matches_text(recorded: str, knob_filter: KnobFilter) -> bool:
    """Compare a knob as text, case-insensitively.

    Ordering operators are refused rather than compared lexicographically:
    ``judge_model >= "claude"`` reads like a mistake, and answering it would
    hide one.
    """
    if knob_filter.operator in _ORDERING_OPERATORS:
        return False
    return _compare(
        left=recorded.casefold(),
        right=knob_filter.value_text.casefold(),
        operator=knob_filter.operator,
    )


_MISSING = object()


def _lookup(scenario_config: dict[str, Any], knob: str) -> Any:
    """Read a knob's recorded value, following dots into nested mappings.

    ``model_overrides.field_observer.model`` is how the CSV export names that
    column and how an analysis dimension addresses it, so a condition has to
    read it the same way. A top-level key wins over the dotted reading, since a
    scenario is free to declare a knob whose name contains a dot.

    Returns :data:`_MISSING` when nothing is there, which is not the same as a
    recorded ``None``.
    """
    if knob in scenario_config:
        return scenario_config[knob]
    if "." not in knob:
        return _MISSING
    current: Any = scenario_config
    for part in knob.split("."):
        if not isinstance(current, dict):
            return _MISSING
        step = cast(dict[str, Any], current)
        if part not in step:
            return _MISSING
        current = step[part]
    return current


def _matches_one(scenario_config: dict[str, Any], knob_filter: KnobFilter) -> bool:
    """Test one filter against a run's recorded config.

    A knob the run never recorded does not match, including under ``!=``: the
    run cannot answer the question, which is not the same as answering it in the
    negative. A knob recorded *as* null did answer, and is handled by
    :func:`_matches_recorded_null`.
    """
    recorded = _lookup(scenario_config=scenario_config, knob=knob_filter.knob)
    if recorded is _MISSING:
        return False
    if _names_null(value_text=knob_filter.value_text):
        return _matches_set_question(recorded=recorded, knob_filter=knob_filter)
    if recorded is None:
        return _matches_recorded_null(knob_filter=knob_filter)
    # bool before the numeric branch: in Python a bool is an int, and comparing
    # True against 1 would make postmortem_enabled>=1 a boolean ordering test.
    if isinstance(recorded, bool):
        return _matches_bool(recorded=recorded, knob_filter=knob_filter)
    if isinstance(recorded, (int, float)):
        return _matches_number(recorded=float(recorded), knob_filter=knob_filter)
    if isinstance(recorded, str):
        return _matches_text(recorded=recorded, knob_filter=knob_filter)
    # A list or a mapping has no scalar comparison. The schema endpoint does not
    # offer one, so reaching here means a hand-written filter.
    return False


def matches_knob_filters(
    scenario_config: dict[str, Any],
    knob_filters: list[KnobFilter],
) -> bool:
    """Whether a run's config satisfies every filter (AND semantics)."""
    return all(
        _matches_one(scenario_config=scenario_config, knob_filter=knob_filter)
        for knob_filter in knob_filters
    )
