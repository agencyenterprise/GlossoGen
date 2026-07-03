"""Builds the ``children`` list for a run-detail response.

Walks the Postgres ``runs`` table for every row whose ``source_run_scenario``
/ ``source_run_dir_name`` columns point at the run currently being viewed,
then enriches each child with manifest-derived boundary info and the eval
report's headline ``round_success*`` measurements. In no-database local mode
(``pool`` is ``None``) the same children are found by scanning the filesystem
and matching each run's manifest-derived source against the parent.
"""

import asyncio
import logging
from pathlib import Path
from typing import Literal, NamedTuple
from uuid import UUID

import orjson

from schmidt.db.pool import DbPool
from schmidt.db.queries import list_children_of_run
from schmidt.evaluation.reports.evaluation_report import load_report
from schmidt.server.runs.discovery import build_summary, discover_runs
from schmidt.server.runs.models import DerivedRunReference, HeadlineMeasurement, RunSummary


class _ChildRunId(NamedTuple):
    """A child run's ``(scenario, run_dir_name)`` identity."""

    scenario: str
    run_dir_name: str

logger = logging.getLogger(__name__)

_REPLACE_MANIFEST_FILENAME = "replace_manifest.json"
_CROSS_RUN_REPLACE_MANIFEST_FILENAME = "cross_run_replace_manifest.json"


DerivationType = Literal["replace_agent", "resume_at_round", "cross_run_replace_agent"]


class _DerivationFields(NamedTuple):
    """All manifest-derived fields needed to populate a :class:`DerivedRunReference`."""

    derivation_type: DerivationType
    round_start: int
    rounds_after_swap: int | None
    rounds_after_resume: int | None
    replaced_agent_id: str | None
    replacement_model: str | None
    replacement_provider: str | None
    imported_model: str | None
    imported_provider: str | None
    source_b_run_id: str | None
    source_b_round_end: int | None


async def build_derived_run_references(
    *,
    pool: DbPool | None,
    runs_dir: Path,
    group_id: UUID,
    parent_scenario: str,
    parent_run_dir_name: str,
) -> list[DerivedRunReference]:
    """Return one reference per child run, newest first.

    Returns an empty list when no children exist or when the parent has
    never been used as a derivation source. In no-database local mode
    (``pool`` is ``None``) children are discovered from the filesystem.
    """
    if pool is None:
        child_ids = await _find_children_on_disk(
            runs_dir=runs_dir,
            parent_scenario=parent_scenario,
            parent_run_dir_name=parent_run_dir_name,
        )
    else:
        async with pool.connection() as conn:
            rows = await list_children_of_run(
                conn=conn,
                group_id=group_id,
                parent_scenario=parent_scenario,
                parent_run_dir_name=parent_run_dir_name,
            )
        child_ids = [
            _ChildRunId(scenario=row.scenario, run_dir_name=row.run_dir_name) for row in rows
        ]
    if not child_ids:
        return []

    tasks = [
        asyncio.create_task(
            _build_reference(
                scenario=child.scenario,
                run_dir_name=child.run_dir_name,
                runs_dir=runs_dir,
            )
        )
        for child in child_ids
    ]
    results = await asyncio.gather(*tasks)
    return [ref for ref in results if ref is not None]


async def _find_children_on_disk(
    *,
    runs_dir: Path,
    parent_scenario: str,
    parent_run_dir_name: str,
) -> list[_ChildRunId]:
    """Scan every run dir and return those whose derivation source is the parent.

    Reuses ``discover_runs`` enrichment, which already reads each run's
    manifest into the summary's source fields, so no manifest is re-parsed here.
    """
    parent_run_id = f"{parent_scenario}/{parent_run_dir_name}"
    summaries = await discover_runs(runs_dir=runs_dir)
    children: list[_ChildRunId] = []
    for summary in summaries:
        if timeline_parent_run_id(summary=summary) != parent_run_id:
            continue
        scenario, run_dir_name = summary.run_id.split("/", 1)
        children.append(_ChildRunId(scenario=scenario, run_dir_name=run_dir_name))
    return children


def timeline_parent_run_id(summary: RunSummary) -> str | None:
    """Return the timeline parent's run id for a derived run, else ``None``.

    Normalizes the multiply-defined provenance: fork, replace-agent, and
    resume-at-round each store the parent under ``source_run_id``; cross-run
    derivations use ``source_a_run_id`` (the timeline parent), matching the
    convention in the runs-index registration path.
    """
    if summary.fork_source is not None:
        return summary.fork_source.source_run_id
    if summary.replace_agent_source is not None:
        return summary.replace_agent_source.source_run_id
    if summary.resume_at_round_source is not None:
        return summary.resume_at_round_source.source_run_id
    if summary.cross_run_replace_agent_source is not None:
        return summary.cross_run_replace_agent_source.source_a_run_id
    return None


async def _build_reference(
    *,
    scenario: str,
    run_dir_name: str,
    runs_dir: Path,
) -> DerivedRunReference | None:
    """Build a single child reference; returns ``None`` if the run dir is unreadable."""
    timestamp_dir = runs_dir / scenario / run_dir_name
    summary = await build_summary(
        scenario_name=scenario,
        timestamp_dir=timestamp_dir,
        evaluation_content_hash=None,
    )
    if summary is None:
        logger.warning(
            "Skipping derived-run reference for %s/%s: build_summary returned None",
            scenario,
            run_dir_name,
        )
        return None

    derivation = _read_derivation_fields(run_dir=timestamp_dir)
    if derivation is None:
        logger.warning(
            "Skipping derived-run reference for %s/%s: no manifest found despite DB linkage",
            scenario,
            run_dir_name,
        )
        return None

    headline_measurements = await _load_headline_measurements(
        scenario_name=scenario,
        run_dir=timestamp_dir,
    )

    target_round_count = _read_target_round_count(scenario_config=summary.scenario_config)

    return DerivedRunReference(
        run_id=summary.run_id,
        derivation_type=derivation.derivation_type,
        round_start=derivation.round_start,
        rounds_after_swap=derivation.rounds_after_swap,
        rounds_after_resume=derivation.rounds_after_resume,
        replaced_agent_id=derivation.replaced_agent_id,
        replacement_model=derivation.replacement_model,
        replacement_provider=derivation.replacement_provider,
        imported_model=derivation.imported_model,
        imported_provider=derivation.imported_provider,
        source_b_run_id=derivation.source_b_run_id,
        source_b_round_end=derivation.source_b_round_end,
        created_at=summary.timestamp,
        status=summary.status,
        current_round=summary.current_round,
        target_round_count=target_round_count,
        total_messages=summary.total_messages,
        total_cost_usd=summary.total_cost_usd,
        labels=summary.labels,
        has_evaluation=summary.has_evaluation,
        headline_measurements=headline_measurements,
    )


def _read_derivation_fields(run_dir: Path) -> _DerivationFields | None:
    """Probe the run dir's manifest files to classify the derivation and pull boundary fields.

    Order matters: cross-run manifests coexist with no replace manifest;
    a plain replace-agent manifest with ``replaced_agent_id is None``
    encodes a resume-at-round derivation. Returns ``None`` when neither
    manifest exists.
    """
    cross_run_path = run_dir / _CROSS_RUN_REPLACE_MANIFEST_FILENAME
    if cross_run_path.exists():
        raw = orjson.loads(cross_run_path.read_bytes())
        return _DerivationFields(
            derivation_type="cross_run_replace_agent",
            round_start=raw["round_start"],
            rounds_after_swap=raw["rounds_after_swap"],
            rounds_after_resume=None,
            replaced_agent_id=raw["replaced_agent_id"],
            replacement_model=None,
            replacement_provider=None,
            imported_model=raw["imported_model"],
            imported_provider=raw["imported_provider"],
            source_b_run_id=raw["source_b_run_id"],
            source_b_round_end=raw["source_b_round_end"],
        )

    replace_path = run_dir / _REPLACE_MANIFEST_FILENAME
    if replace_path.exists():
        raw = orjson.loads(replace_path.read_bytes())
        replaced_agent_id = raw.get("replaced_agent_id")
        if replaced_agent_id is None:
            return _DerivationFields(
                derivation_type="resume_at_round",
                round_start=raw["round_start"],
                rounds_after_swap=None,
                rounds_after_resume=raw["rounds_after_swap"],
                replaced_agent_id=None,
                replacement_model=None,
                replacement_provider=None,
                imported_model=None,
                imported_provider=None,
                source_b_run_id=None,
                source_b_round_end=None,
            )
        return _DerivationFields(
            derivation_type="replace_agent",
            round_start=raw["round_start"],
            rounds_after_swap=raw["rounds_after_swap"],
            rounds_after_resume=None,
            replaced_agent_id=replaced_agent_id,
            replacement_model=raw["replacement_model"],
            replacement_provider=raw["replacement_provider"],
            imported_model=None,
            imported_provider=None,
            source_b_run_id=None,
            source_b_round_end=None,
        )

    return None


def _read_target_round_count(scenario_config: dict[str, object]) -> int | None:
    """Pull ``round_count`` from the run's scenario config when present and well-typed."""
    raw = scenario_config.get("round_count")
    if isinstance(raw, int):
        return raw
    return None


async def _load_headline_measurements(
    *,
    scenario_name: str,
    run_dir: Path,
) -> list[HeadlineMeasurement]:
    """Load up to three ``round_success``-family measurements from the eval report.

    Returns ``[]`` when no report file exists, the file is unreadable,
    or none of the metric names match the ``round_success`` prefix.
    """
    report_path = run_dir / f"{scenario_name}_report.json"
    try:
        report = await load_report(report_path=report_path)
    except Exception:
        logger.exception("Failed to load eval report at %s", report_path)
        return []
    if report is None:
        return []

    after_resume: list[HeadlineMeasurement] = []
    base: list[HeadlineMeasurement] = []
    for measurement in report.measurements:
        if measurement.metric_name.startswith("round_success_after_resume"):
            after_resume.append(
                HeadlineMeasurement(
                    metric_name=measurement.metric_name,
                    score=measurement.score,
                    score_unit=measurement.score_unit,
                    summary=measurement.summary,
                )
            )
        elif measurement.metric_name.startswith("round_success"):
            base.append(
                HeadlineMeasurement(
                    metric_name=measurement.metric_name,
                    score=measurement.score,
                    score_unit=measurement.score_unit,
                    summary=measurement.summary,
                )
            )

    after_resume.sort(key=lambda m: m.metric_name)
    base.sort(key=lambda m: m.metric_name)
    return (after_resume + base)[:3]
