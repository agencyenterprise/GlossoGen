"""What a client asks an export for.

Which runs is a tagged union of two shapes, not one shape holding both a filter set
and an id list. "Both were given" is then unrepresentable, so there is no precedence
rule to document or to get wrong. It also matches how the choice gets made: either
these specific runs, or everything matching what I am looking at.

Columns are named explicitly, with no "all" flag. A request that lists its columns is
reproducible: the same body exports the same table later, and the export can record
verbatim what it was asked for. "All columns" is the caller echoing back the keys the
preview offered.
"""

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from glossogen.knob_filter import (
    KnobFilter,
    KnobFilterParseError,
    parse_knob_filters,
)
from glossogen.models.event import RunStatus


class ExportFrame(str, Enum):
    """One CSV table shape an export can emit."""

    RUN_LEVEL = "run_level"
    ROUND_LEVEL = "round_level"
    AGENT_LEVEL = "agent_level"
    MESSAGE_LEVEL = "message_level"
    ROUND_CONTEXT = "round_context"


class FilterRunSelection(BaseModel):
    """Runs named by the same filters the runs list uses.

    Mirrors the runs list without paging: ``scenario`` is OR-matched, ``labels``
    are AND-matched, ``run_id_contains`` is a case-insensitive substring of
    ``scenario/run_dir_name``, ``status`` restricts to one run status, and
    ``contains_agent_id`` keeps runs that registered that agent. Each ``knob``
    entry is one ``<knob><operator><value>`` condition on the run's recorded
    ``scenario_config``, and every one of them has to hold.

    Every filter empty means every run the caller can see.

    The set matches the list's own filters, so any selection the list can show is one
    the export can reproduce.
    """

    # Extra keys are refused so the two shapes really are exclusive: without
    # this, a filter selection carrying run_ids is accepted and the ids ignored.
    model_config = ConfigDict(extra="forbid")

    kind: Literal["filters"]
    scenario: list[str]
    labels: list[str]
    run_id_contains: str | None
    status: RunStatus | None
    contains_agent_id: str | None
    knob: list[str]

    @field_validator("knob")
    @classmethod
    def _knob_conditions_parse(cls, raw_filters: list[str]) -> list[str]:
        """Refuse a condition that carries no operator.

        Validating on the model rather than at each call site is what makes the
        three export endpoints answer 422 instead of 500, and makes the CLI fail
        with the same message rather than dropping the condition and exporting a
        wider set than was asked for.
        """
        try:
            parse_knob_filters(raw_filters=raw_filters)
        except KnobFilterParseError as exc:
            raise ValueError(str(exc)) from exc
        return raw_filters

    def parsed_knob_conditions(self) -> list[KnobFilter]:
        """The parsed form of ``knob``. Validation already proved every entry parses."""
        return parse_knob_filters(raw_filters=self.knob)


class ExplicitRunSelection(BaseModel):
    """Runs named one by one as ``scenario/run_dir_name`` ids."""

    # Extra keys are refused so the two shapes really are exclusive: without
    # this, a filter selection carrying run_ids is accepted and the ids ignored.
    model_config = ConfigDict(extra="forbid")

    kind: Literal["explicit"]
    run_ids: list[str]


RunSelection = Annotated[
    FilterRunSelection | ExplicitRunSelection,
    Field(discriminator="kind"),
]


class ExportPreviewRequest(BaseModel):
    """Body for the export preview.

    ``include_raw_size_estimate`` opts into walking the selected run directories
    for their on-disk size. It is the only part of the preview that costs one
    filesystem stat per file, so the CSV side leaves it off.

    ``include_logs`` is what the estimate is taken with. The logs are roughly half
    the size of a run folder again, so an estimate that ignored it would sit under
    the checkbox that changes it and never move.
    """

    selection: RunSelection
    include_raw_size_estimate: bool
    include_logs: bool


class RawExportRequest(BaseModel):
    """Body for the raw run-folder zip."""

    selection: RunSelection
    include_logs: bool


class CsvExportRequest(BaseModel):
    """Body for the CSV export.

    ``frames`` picks which tables to emit. ``columns`` names the run-context
    columns to carry, and ``metrics`` the evaluator metrics, which are one column
    each on every table that carries scores. ``repeat_run_columns`` copies the run
    context onto every row of the per-round, per-agent and per-message tables so
    they read without joining back to the run-level table.
    ``include_metric_summaries`` adds each metric's unit and one-line rollup at run
    level and its per-observation note on the other tables, which roughly triples
    the run-level table's width.

    ``metrics`` reaches neither the message nor the round-context table, whose
    cells are what an agent said and what it was told rather than measurements.
    """

    selection: RunSelection
    frames: list[ExportFrame]
    columns: list[str]
    metrics: list[str]
    repeat_run_columns: bool
    include_metric_summaries: bool
