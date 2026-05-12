"""Consolidate per-run free-form open-coding labels into a shared ontology.

Reads each input run's ``communication_open_coding.json`` sidecar
(produced by the ``communication_open_coding`` metric), pools the
free-form labels with provenance, and asks an LLM to consolidate them
into a versioned taxonomy. The resulting
:class:`CommunicationOntology` JSON is written under
``analysis/communication_ontology/`` and is the input to pass 3
(``communication_feature_presence``).

Run-id selection is explicit only — pass ``--run-id <id>`` repeatedly
or ``--run-ids-file <path>`` (one id per line). This avoids accidental
inclusion of unrelated runs (label-glob disasters as warned in
``CLAUDE.md``).

Usage:

    VIRTUAL_ENV= uv run --no-sync python scripts/consolidate_communication_ontology.py \
        --run-id veyru/1742234567 \
        --run-id veyru/1742300000 \
        --runs-dir ./runs \
        --output analysis/communication_ontology/2026-05-11_test.json \
        --model claude-haiku-4-5-20251001 \
        --provider anthropic
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from dotenv import load_dotenv
from pydantic import BaseModel

from schmidt.evaluation.prompts.prompt_renderer import render_evaluator_prompt
from schmidt.llm.provider import LLMMessage
from schmidt.llm.provider_factory import create_provider
from schmidt.scenarios.veyru.evaluation.metrics.communication.label_models import (
    CommunicationOntology,
    CommunicationOntologyConsolidationOutput,
    CommunicationOpenCodingSidecar,
)
from schmidt.scenarios.veyru.evaluation.prompts.prompt_renderer import render_veyru_prompt

# Walk up from this file to the repo root so we load the canonical project
# ``.env`` rather than ``scripts/.env`` (which exists for unrelated tools and
# would mask the project's API keys via dotenv's find-dotenv default).
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger(__name__)

_OPEN_CODING_SIDECAR = "communication_open_coding.json"


class LabelPoolEntry(BaseModel):
    """One row in the deduplicated label pool sent to the consolidation judge.

    Entries are keyed by exact label ``text``: every run that emitted the
    same verbatim label is collapsed into a single row, with ``run_ids``
    listing all of them and ``evidence_count_total`` summing the
    per-run citation counts. ``sample_quotes`` carries up to three
    verbatim quotes pulled from across the contributing runs so the
    consolidation judge has surface-form evidence without ballooning
    the prompt to one row per (run, label).
    """

    text: str
    run_ids: list[str]
    evidence_count_total: int
    sample_quotes: list[str]


class LoadedSidecars(NamedTuple):
    """All open-coding sidecars loaded for a consolidation run."""

    sidecars: list[CommunicationOpenCodingSidecar]
    label_pool: list[LabelPoolEntry]


def _parse_args() -> argparse.Namespace:
    """Define and parse the CLI flags."""
    parser = argparse.ArgumentParser(
        description=(
            "Consolidate communication open-coding labels into a versioned "
            "ontology. Reads each run's communication_open_coding.json "
            "sidecar and writes one CommunicationOntology JSON file."
        )
    )
    parser.add_argument(
        "--run-id",
        dest="run_ids",
        action="append",
        default=[],
        help=(
            "Run id in ``<scenario>/<timestamp>`` form. May be passed "
            "multiple times. Combined with --run-ids-file."
        ),
    )
    parser.add_argument(
        "--run-ids-file",
        dest="run_ids_file",
        type=str,
        default=None,
        help="Path to a text file with one run id per line.",
    )
    parser.add_argument(
        "--runs-dir",
        dest="runs_dir",
        type=str,
        required=True,
        help="Root directory containing run subdirectories (e.g. ./runs).",
    )
    parser.add_argument(
        "--output",
        dest="output_path",
        type=str,
        required=True,
        help=(
            "Path to write the consolidated ontology JSON (typically "
            "analysis/communication_ontology/<version>.json)."
        ),
    )
    parser.add_argument(
        "--model",
        dest="model",
        type=str,
        required=True,
        help="LLM model identifier for the consolidation judge.",
    )
    parser.add_argument(
        "--provider",
        dest="provider",
        type=str,
        required=True,
        help="LLM provider for the consolidation judge.",
    )
    parser.add_argument(
        "--inference-provider",
        dest="inference_provider",
        type=str,
        default=None,
        help="Optional HuggingFace inference backend (together, fireworks-ai, ...).",
    )
    parser.add_argument(
        "--reasoning-effort",
        dest="reasoning_effort",
        type=str,
        choices=["low", "medium", "high"],
        default=None,
        help="Reasoning effort for OpenAI reasoning models.",
    )
    parser.add_argument(
        "--min-runs",
        dest="min_runs",
        type=int,
        default=1,
        help=(
            "Drop label texts emitted by fewer than this many distinct runs "
            "from the pool before consolidating. Set to 2+ on large corpora "
            "to filter LLM phrasing-variation singletons (the long tail of "
            "labels seen in only one run) and keep the prompt within the "
            "judge's context limit. Default 1 (keep everything)."
        ),
    )
    return parser.parse_args()


def _collect_run_ids(args: argparse.Namespace) -> list[str]:
    """Combine ``--run-id`` repeated values and ``--run-ids-file`` lines."""
    run_ids: list[str] = list(args.run_ids)
    if args.run_ids_file:
        for line in Path(args.run_ids_file).read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                run_ids.append(stripped)
    if not run_ids:
        raise ValueError("No run ids provided (--run-id or --run-ids-file).")
    seen: set[str] = set()
    deduped: list[str] = []
    for run_id in run_ids:
        if run_id not in seen:
            seen.add(run_id)
            deduped.append(run_id)
    return deduped


def _load_sidecars(runs_dir: Path, run_ids: list[str], min_runs: int) -> LoadedSidecars:
    """Read each run's open-coding sidecar and build a deduplicated label pool.

    Pre-dedupe by exact label ``text``: runs that emit verbatim-identical
    labels collapse into one pool row carrying the union of their
    contributing run ids, the sum of their per-run citation counts, and
    up to three sample quotes drawn from across them.

    ``min_runs`` drops the long tail of label texts emitted by fewer
    than that many distinct runs. On large corpora (400+ runs) the
    singleton tail is dominated by LLM phrasing variation rather than
    real cross-run mechanisms, and including it can push the prompt past
    the judge's context limit. ``min_runs=1`` keeps everything.
    """
    sidecars: list[CommunicationOpenCodingSidecar] = []
    by_text: dict[str, _DedupAccumulator] = {}
    missing: list[str] = []
    for run_id in run_ids:
        sidecar_path = runs_dir / run_id / _OPEN_CODING_SIDECAR
        if not sidecar_path.exists():
            missing.append(run_id)
            continue
        sidecar = CommunicationOpenCodingSidecar.model_validate_json(
            sidecar_path.read_text(encoding="utf-8")
        )
        sidecars.append(sidecar)
        for label in sidecar.labels:
            accumulator = by_text.setdefault(label.text, _DedupAccumulator())
            accumulator.run_ids.append(sidecar.run_id)
            accumulator.evidence_count_total += len(label.evidence)
            for citation in label.evidence:
                accumulator.candidate_quotes.append(citation.quote)
    if missing:
        raise FileNotFoundError(
            "Missing communication_open_coding.json for run(s): "
            + ", ".join(missing)
            + ". Run `schmidt evaluate ... --metrics communication_open_coding` first."
        )
    pre_filter_unique = len(by_text)
    label_pool = [
        LabelPoolEntry(
            text=text,
            run_ids=sorted(set(acc.run_ids)),
            evidence_count_total=acc.evidence_count_total,
            sample_quotes=acc.candidate_quotes[:3],
        )
        for text, acc in sorted(by_text.items())
        if len(set(acc.run_ids)) >= min_runs
    ]
    if min_runs > 1:
        logger.info(
            "Label pool: %d unique texts before filter, %d after dropping "
            "texts emitted by fewer than %d runs.",
            pre_filter_unique,
            len(label_pool),
            min_runs,
        )
    if not label_pool:
        if min_runs > 1:
            raise ValueError("Label pool empty after min_runs filter — lower --min-runs.")
        raise ValueError("All sidecars loaded but no labels found in any of them.")
    return LoadedSidecars(sidecars=sidecars, label_pool=label_pool)


class _DedupAccumulator:
    """Per-text scratch state while building the deduplicated label pool."""

    def __init__(self) -> None:
        self.run_ids: list[str] = []
        self.evidence_count_total: int = 0
        self.candidate_quotes: list[str] = []


async def _consolidate(
    label_pool: list[LabelPoolEntry],
    source_run_count: int,
    model: str,
    provider: str,
    inference_provider: str | None,
    reasoning_effort: str | None,
) -> CommunicationOntologyConsolidationOutput:
    """Render the consolidation prompt and call the judge once."""
    llm_provider = create_provider(
        provider_name=provider,
        model=model,
        inference_provider=inference_provider,
        reasoning_effort=reasoning_effort,
    )
    user_prompt = render_veyru_prompt(
        template_name="communication_ontology_consolidate_user.jinja",
        template_variables={
            "label_pool": label_pool,
            "source_run_count": source_run_count,
        },
    )
    system_prompt = render_evaluator_prompt(
        template_name="evaluator_system.jinja",
        template_variables={},
    )
    logger.debug(
        "consolidate_communication_ontology LLM input system_prompt=%s user_prompt=%s",
        system_prompt,
        user_prompt,
    )
    result = await llm_provider.generate_structured(
        system_prompt=system_prompt,
        messages=[LLMMessage(role="user", content=user_prompt)],
        output_schema=CommunicationOntologyConsolidationOutput,
    )
    logger.debug(
        "consolidate_communication_ontology LLM output=%s",
        result.model_dump_json(),
    )
    return result


def _build_ontology(
    output_path: Path,
    source_run_ids: list[str],
    consolidation: CommunicationOntologyConsolidationOutput,
) -> CommunicationOntology:
    """Wrap the judge output with version metadata before writing to disk."""
    version = output_path.stem
    return CommunicationOntology(
        version=version,
        generated_at=datetime.now(tz=timezone.utc),
        source_run_ids=source_run_ids,
        categories=consolidation.categories,
    )


async def _main() -> int:
    """Entry point — returns an exit code for ``sys.exit``."""
    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()
    runs_dir = Path(args.runs_dir)
    output_path = Path(args.output_path)
    if not runs_dir.exists():
        logger.error("Runs directory not found: %s", runs_dir)
        return 1
    output_path.parent.mkdir(parents=True, exist_ok=True)

    run_ids = _collect_run_ids(args=args)
    loaded = _load_sidecars(runs_dir=runs_dir, run_ids=run_ids, min_runs=args.min_runs)
    logger.info(
        "Loaded %d sidecar(s) totalling %d label(s) from %d run(s).",
        len(loaded.sidecars),
        len(loaded.label_pool),
        len(run_ids),
    )

    consolidation = await _consolidate(
        label_pool=loaded.label_pool,
        source_run_count=len(loaded.sidecars),
        model=args.model,
        provider=args.provider,
        inference_provider=args.inference_provider,
        reasoning_effort=args.reasoning_effort,
    )
    ontology = _build_ontology(
        output_path=output_path,
        source_run_ids=run_ids,
        consolidation=consolidation,
    )
    output_path.write_text(ontology.model_dump_json(indent=2) + "\n")
    logger.info(
        "Wrote ontology version=%s with %d categories to %s",
        ontology.version,
        len(ontology.categories),
        output_path,
    )
    logger.info("Consolidation explanation: %s", consolidation.explanation)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
