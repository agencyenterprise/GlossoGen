"""Builds the ``children`` list for a run-detail response.

Walks the Postgres ``runs`` table for every row whose ``source_run_scenario``
/ ``source_run_dir_name`` columns point at the run currently being viewed,
then enriches each child with manifest-derived boundary info and the headline
``round_success*`` scores among the summary's evaluation scores. In no-database
local mode (``pool`` is ``None``) the same children are found by scanning the
filesystem and matching each run's manifest-derived source against the parent.
"""

import asyncio
import logging
from pathlib import Path
from typing import NamedTuple
from uuid import UUID

from pydantic import ValidationError

from glossogen.db.pool import DbPool
from glossogen.db.queries import list_children_of_run
from glossogen.run_storage.derivation_manifest_reader import (
    read_cross_run_replace_agent_source,
    read_derivation_fields,
    read_fork_at_round_source,
    read_fork_source,
    read_replace_agent_source,
)
from glossogen.run_storage.run_discovery import (
    RunDescriptor,
    build_summary,
    discover_run_descriptors,
)
from glossogen.run_storage.run_identity import compose_run_id
from glossogen.run_storage.run_summary_models import (
    CrossRunReplaceAgentSource,
    EvaluationScore,
    ForkAtRoundSource,
    ForkSource,
    ReplaceAgentSource,
    RunSummary,
)
from glossogen.scenario_contract.loader import find_scenario_class
from glossogen.server.runs.models import DerivedRunReference


class _ChildRunId(NamedTuple):
    """A child run's ``(scenario, run_dir_name)`` identity."""

    scenario: str
    run_dir_name: str


logger = logging.getLogger(__name__)


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
    """Return the runs on disk whose timeline parent is the given run, newest first.

    Reads only each run's derivation manifests, in a worker thread. Building a
    summary per run to get at the same sources would also read its labels, note,
    evaluation manifest and report, for every run on disk on every run-detail
    request. The children found here are enriched afterwards by
    :func:`_build_reference`, which drops a run whose summary cannot be built.
    """
    return await asyncio.to_thread(
        _find_children_on_disk_sync,
        runs_dir,
        compose_run_id(scenario_name=parent_scenario, run_dir_name=parent_run_dir_name),
    )


def _find_children_on_disk_sync(runs_dir: Path, parent_run_id: str) -> list[_ChildRunId]:
    """Blocking core of :func:`_find_children_on_disk`.

    Orders ties within one second by scenario and run directory name, ascending,
    the same order :func:`~glossogen.run_storage.run_discovery.discover_runs`
    gives.
    """
    children = [
        derived.descriptor
        for derived in derived_runs_on_disk(
            runs_dir=runs_dir, descriptors=discover_run_descriptors(runs_dir=runs_dir)
        )
        if derived.parent_run_id == parent_run_id
    ]
    children.sort(key=lambda descriptor: (descriptor.scenario_name, descriptor.run_dir_name))
    children.sort(key=lambda descriptor: descriptor.timestamp, reverse=True)
    return [
        _ChildRunId(scenario=descriptor.scenario_name, run_dir_name=descriptor.run_dir_name)
        for descriptor in children
    ]


class DerivedRunOnDisk(NamedTuple):
    """A run on disk that has a timeline parent, with that parent's run id."""

    descriptor: RunDescriptor
    parent_run_id: str


def derived_runs_on_disk(
    runs_dir: Path, descriptors: list[RunDescriptor]
) -> list[DerivedRunOnDisk]:
    """Return each of ``descriptors`` that has a timeline parent, in the order given.

    Blocking. Reads only each run's derivation manifests, never its event log,
    labels or evaluation. A run whose manifests cannot be read is logged and
    left out rather than failing the caller's page.
    """
    derived: list[DerivedRunOnDisk] = []
    for descriptor in descriptors:
        run_dir = runs_dir / descriptor.scenario_name / descriptor.run_dir_name
        try:
            parent = _timeline_parent_on_disk(run_dir=run_dir)
        except Exception:
            logger.exception("Could not read the derivation manifests at %s", run_dir)
            continue
        if parent is not None:
            derived.append(DerivedRunOnDisk(descriptor=descriptor, parent_run_id=parent))
    return derived


def _timeline_parent_on_disk(run_dir: Path) -> str | None:
    """Return the timeline parent's run id read off a run's manifests, else ``None``.

    Reads the same manifests, through the same readers, that fill a summary's
    source fields, and applies :func:`_timeline_parent_of_sources` to them.
    """
    return _timeline_parent_of_sources(
        fork_source=read_fork_source(run_dir=run_dir),
        replace_agent_source=read_replace_agent_source(run_dir=run_dir),
        fork_at_round_source=read_fork_at_round_source(run_dir=run_dir),
        cross_run_replace_agent_source=read_cross_run_replace_agent_source(run_dir=run_dir),
    )


def timeline_parent_run_id(summary: RunSummary) -> str | None:
    """Return the timeline parent's run id for a derived run's summary, else ``None``."""
    return _timeline_parent_of_sources(
        fork_source=summary.fork_source,
        replace_agent_source=summary.replace_agent_source,
        fork_at_round_source=summary.fork_at_round_source,
        cross_run_replace_agent_source=summary.cross_run_replace_agent_source,
    )


def _timeline_parent_of_sources(
    fork_source: ForkSource | None,
    replace_agent_source: ReplaceAgentSource | None,
    fork_at_round_source: ForkAtRoundSource | None,
    cross_run_replace_agent_source: CrossRunReplaceAgentSource | None,
) -> str | None:
    """Return the timeline parent's run id given a run's derivation sources, else ``None``.

    Normalizes the multiply-defined provenance: fork, replace-agent, and
    fork-at-round each store the parent under ``source_run_id``; cross-run
    derivations use ``source_a_run_id`` (the timeline parent), matching the
    convention in the runs-index registration path.
    """
    if fork_source is not None:
        return fork_source.source_run_id
    if replace_agent_source is not None:
        return replace_agent_source.source_run_id
    if fork_at_round_source is not None:
        return fork_at_round_source.source_run_id
    if cross_run_replace_agent_source is not None:
        return cross_run_replace_agent_source.source_a_run_id
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

    derivation = read_derivation_fields(run_dir=timestamp_dir)
    if derivation is None:
        logger.warning(
            "Skipping derived-run reference for %s/%s: no manifest found despite DB linkage",
            scenario,
            run_dir_name,
        )
        return None

    if summary.evaluation_scores is None:
        headline_measurements = []
    else:
        headline_measurements = headline_measurements_of(scores=summary.evaluation_scores)

    target_round_count = _read_target_round_count(
        scenario_name=scenario, scenario_config=summary.scenario_config
    )

    return DerivedRunReference(
        run_id=summary.run_id,
        derivation_type=derivation.derivation_type,
        after_round=derivation.after_round,
        rounds_after=derivation.rounds_after,
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
        evaluation_scores=summary.evaluation_scores,
        headline_measurements=headline_measurements,
    )


def _read_target_round_count(scenario_name: str, scenario_config: dict[str, object]) -> int | None:
    """Return the run's ``round_count`` knob, read through the scenario's knobs model.

    Returns None when the run recorded no config yet, when the scenario is not
    installed, or when the recorded config no longer validates against the
    knobs model (a run older than a required knob). The listing still renders
    in those cases, without the target.
    """
    if not scenario_config:
        return None
    scenario_cls = find_scenario_class(name=scenario_name)
    if scenario_cls is None:
        return None
    try:
        knobs = scenario_cls.knobs_model().model_validate(
            scenario_cls.strip_unknown_knobs(config=dict(scenario_config))
        )
    except ValidationError:
        logger.exception(
            "Recorded %s config does not validate; omitting round count", scenario_name
        )
        return None
    return knobs.round_count


def headline_measurements_of(scores: list[EvaluationScore]) -> list[EvaluationScore]:
    """Select up to three ``round_success``-family scores for a derived run's row.

    ``round_success_after_resume*`` scores come first, then the other
    ``round_success*`` scores, each group sorted by metric name.
    """
    after_resume: list[EvaluationScore] = []
    base: list[EvaluationScore] = []
    for score in scores:
        if score.metric_name.startswith("round_success_after_resume"):
            after_resume.append(score)
        elif score.metric_name.startswith("round_success"):
            base.append(score)
    after_resume.sort(key=lambda m: m.metric_name)
    base.sort(key=lambda m: m.metric_name)
    return (after_resume + base)[:3]
