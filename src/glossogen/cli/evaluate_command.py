"""The ``evaluate`` subcommand: score a finished run's log with metrics."""

import argparse
import logging
import os
from pathlib import Path

from glossogen.cli.subcommand_parsers import SubcommandParsers
from glossogen.eval_manifest import delete_eval_manifest, write_eval_manifest
from glossogen.evaluation.evaluation_judge_settings import (
    add_judge_settings_argument,
    parse_judge_settings,
)
from glossogen.evaluation.log_reader import extract_scenario_config, load_events
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.scenario_evaluation_runner import run_scenario_evaluation
from glossogen.model_catalog import JUDGE_PROVIDERS
from glossogen.run_config.knobs_resolution import resolve_knobs_overrides
from glossogen.run_file_paths import evaluation_report_path, event_log_path
from glossogen.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


def add_evaluate_parser(subparsers: SubcommandParsers, scenario_names: list[str]) -> None:
    """Add the ``evaluate`` subcommand and its flags."""
    evaluate_parser = subparsers.add_parser("evaluate", help="Evaluate a simulation log")
    evaluate_parser.add_argument(
        "scenario_name",
        type=str,
        choices=scenario_names,
        help="Name of the scenario to evaluate",
    )
    evaluate_parser.add_argument(
        "--run-dir",
        type=str,
        required=True,
        help="Path to the run directory (e.g. runs/veyru/1742234567)",
    )
    evaluate_parser.add_argument(
        "--metrics", type=str, required=True, help="Comma-separated metric names"
    )
    evaluate_parser.add_argument("--model", type=str, required=True, help="LLM model identifier")
    evaluate_parser.add_argument(
        "--provider",
        type=str,
        required=True,
        choices=[provider.value for provider in JUDGE_PROVIDERS],
        help="Provider of the LLM judge",
    )
    evaluate_parser.add_argument(
        "--inference-provider",
        type=str,
        help="HuggingFace inference provider backend (e.g. together, fireworks-ai, cerebras)",
    )
    add_judge_settings_argument(parser=evaluate_parser)
    evaluate_parser.add_argument(
        "--probe-round",
        dest="probe_round",
        type=int,
        default=None,
        help=(
            "Cutoff for the protocol_probe metric: drops every tool call whose "
            "round_number >= R, so reconstructed history covers rounds 1..R-1 "
            "(inclusive). Pass --probe-round=R+1 to capture the agent's state "
            "at the END of round R. Omit for the full end-of-run history."
        ),
    )
    evaluate_parser.add_argument(
        "--probe-replicas",
        dest="probe_replicas",
        type=int,
        default=None,
        help=(
            "Number of independent replicas the protocol_probe metric runs per "
            "(agent, question). Required when --metrics includes protocol_probe."
        ),
    )
    evaluate_parser.add_argument(
        "--ontology-path",
        dest="ontology_path",
        type=str,
        default=None,
        help=(
            "Path to a consolidated communication-feature ontology JSON file, "
            "pinning communication_feature_presence to one ontology. Omit it and "
            "the metric reads the most recently modified JSON under "
            "runs/<scenario>/_ontology/."
        ),
    )
    evaluate_parser.add_argument(
        "--knobs",
        type=str,
        default=None,
        help=(
            "Optional scenario knob overrides (a preset name or a path to a "
            "JSON file) merged onto the run's recorded scenario_config before validating the "
            "scenario. Useful for evaluating runs whose schema gained a "
            "required knob after the run was created (e.g. veyru's "
            "easy_round_numbers on pre-existing baselines)."
        ),
    )


async def handle_evaluate(
    args: argparse.Namespace,
    scenario_cls: type[SimulationScenario],
) -> None:
    """Run the specified metrics against a simulation log and write a JSON report.

    Reconstructs the scenario from the config stored in the JSONL event log,
    so the evaluate command does not need scenario-specific CLI flags.
    Writes an eval manifest while running so the web UI can detect progress.
    """
    metric_names = args.metrics.split(",")
    run_dir = Path(args.run_dir)
    log_path = event_log_path(run_dir=run_dir, scenario_name=args.scenario_name)
    report_path = evaluation_report_path(run_dir=run_dir, scenario_name=args.scenario_name)

    events = await load_events(log_path=log_path)
    config = scenario_cls.strip_unknown_knobs(config=dict(extract_scenario_config(events=events)))
    overrides = resolve_knobs_overrides(scenario_cls=scenario_cls, requested=args.knobs)
    if overrides is not None:
        config.update(overrides.config)
        logger.info(
            "Merged --knobs overrides from %s into scenario_config: keys=%s",
            overrides.source,
            sorted(overrides.config),
        )
    scenario = scenario_cls.create_from_config(config=config)

    judge_settings = parse_judge_settings(raw=args.judge_settings)
    options = MetricRunOptions(
        probe_round=args.probe_round,
        probe_replicas=args.probe_replicas,
        ontology_path=Path(args.ontology_path) if args.ontology_path else None,
    )

    write_eval_manifest(run_dir=run_dir, pid=os.getpid())
    try:
        logger.info("Evaluating %s with metrics: %s", args.scenario_name, args.metrics)
        await run_scenario_evaluation(
            scenario=scenario,
            log_path=log_path,
            metric_names=metric_names,
            report_path=report_path,
            model=args.model,
            provider_name=args.provider,
            inference_provider=args.inference_provider,
            judge_settings=judge_settings,
            options=options,
        )
        logger.info("Evaluation complete. Report written to %s", report_path)
    finally:
        delete_eval_manifest(run_dir=run_dir)
