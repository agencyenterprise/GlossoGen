"""The ``replace-agent``, ``cross-run-replace-agent`` and ``fork-at-round``
subcommands: deriving a new run from a finished one at a round boundary.
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from glossogen.cli.subcommand_parsers import SubcommandParsers
from glossogen.db.local_tenant import LOCAL_GROUP_SLUG
from glossogen.db.run_registry import register_run_standalone
from glossogen.evaluation.log_reader import load_events
from glossogen.model_catalog import SIMULATION_PROVIDERS
from glossogen.models.event import (
    AgentRegistered,
    ChannelCreated,
    RoundAdvanced,
    RunStatus,
    SimulationStarted,
)
from glossogen.run_config.knobs_resolution import resolve_knobs_overrides
from glossogen.run_derivation.cross_run_replace_agent import (
    CrossRunReplaceAgentRequest as CrossRunCoreRequest,
)
from glossogen.run_derivation.cross_run_replace_agent import cross_run_replace_agent_in_run
from glossogen.run_derivation.replace_agent import ReplaceAgentRequest as ReplaceAgentCoreRequest
from glossogen.run_derivation.replace_agent import replace_agent_in_run
from glossogen.run_file_paths import event_log_path
from glossogen.scenario_loader import get_scenario_class
from glossogen.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


def add_replace_agent_parser(subparsers: SubcommandParsers, scenario_names: list[str]) -> None:
    """Add the ``replace-agent`` subcommand and its flags."""
    replace_parser = subparsers.add_parser(
        "replace-agent",
        help="Replace one agent in a finished run from a target message and re-run",
    )
    replace_parser.add_argument(
        "scenario_name",
        type=str,
        choices=scenario_names,
        help="Name of the scenario the source run belongs to",
    )
    replace_parser.add_argument(
        "--source-run-dir",
        type=str,
        required=True,
        help="Path to the source run directory (e.g. runs/veyru/1742234567)",
    )
    replace_parser.add_argument(
        "--after-round",
        dest="after_round",
        type=int,
        required=True,
        help=(
            "The fork boundary: rounds 1..N stay complete, verdict and "
            "postmortem included, and the replacement agent enters round N+1."
        ),
    )
    replace_parser.add_argument(
        "--replaced-agent-id",
        type=str,
        required=True,
        help="agent_id of the agent to restart with empty history",
    )
    replace_parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Model identifier for the replacement agent",
    )
    replace_parser.add_argument(
        "--provider",
        type=str,
        required=True,
        choices=[provider.value for provider in SIMULATION_PROVIDERS],
        help="Provider for the replacement agent",
    )
    replace_parser.add_argument(
        "--runs-dir",
        type=str,
        required=True,
        help="Root directory where the new run is written",
    )
    replace_parser.add_argument(
        "--knobs",
        type=str,
        help=(
            "Optional scenario knob overrides: a preset name the scenario "
            "ships, or a path to a JSON file. A round_count inside it sets "
            "the fork's total rounds when --rounds-after is omitted, and "
            "must agree with it when both are given"
        ),
    )
    replace_parser.add_argument(
        "--visible-history-channel",
        dest="visible_history_channels",
        action="append",
        default=None,
        help=(
            "Channel ID for which the replaced agent retains visibility of prior "
            "messages on resume. Repeatable. When the flag is omitted entirely, "
            "the per-channel defaults from the source run's "
            "`replace_agent_default_channel_visibility` knob are used (channels "
            "that map to false get wiped; the rest stay visible)."
        ),
    )
    replace_parser.add_argument(
        "--rounds-after",
        dest="rounds_after",
        type=int,
        default=None,
        help=(
            "Number of new rounds the fork plays. round_count is set to "
            "after_round + rounds_after. When omitted, a round_count carried "
            "by --knobs sets the total instead, and with neither the default "
            "is source_round_count - after_round (the source rounds past the "
            "boundary); forking after the source's final round requires one "
            "of the explicit forms."
        ),
    )
    replace_parser.add_argument(
        "--history-from-round",
        dest="history_from_round",
        type=int,
        default=None,
        help=(
            "Window the replaced agent's history: it keeps its predecessor's "
            "tool calls only from this round onward. On every channel in the "
            "resolved visible set, read_channel returns are dropped and "
            "send_message is kept from this round; every other tool call "
            "(read_notifications, the scenario's own tools) from an earlier round "
            "is dropped, which is what windows a seat that belongs to no channel. "
            "For the previous P rounds before the boundary, pass "
            "after_round - P + 1; after_round + 1 keeps no prior history. When "
            "omitted, the predecessor's whole tool-call history is kept."
        ),
    )
    replace_parser.add_argument(
        "--group-slug",
        type=str,
        default=LOCAL_GROUP_SLUG,
        help=f"Tenant group slug that owns the new run (default: {LOCAL_GROUP_SLUG})",
    )


def add_cross_run_replace_agent_parser(
    subparsers: SubcommandParsers, scenario_names: list[str]
) -> None:
    """Add the ``cross-run-replace-agent`` subcommand and its flags."""
    cross_run_parser = subparsers.add_parser(
        "cross-run-replace-agent",
        help=(
            "Import an agent from one finished run into another at a chosen "
            "round boundary, retaining its full pydantic-ai history"
        ),
    )
    cross_run_parser.add_argument(
        "scenario_name",
        type=str,
        choices=scenario_names,
        help="Name of the scenario both source runs belong to",
    )
    cross_run_parser.add_argument(
        "--source-a-run-dir",
        type=str,
        required=True,
        help="Path to the target run directory whose timeline is being modified",
    )
    cross_run_parser.add_argument(
        "--source-b-run-dir",
        type=str,
        required=True,
        help="Path to the run directory the imported agent comes from",
    )
    cross_run_parser.add_argument(
        "--after-round",
        dest="after_round",
        type=int,
        required=True,
        help=(
            "The fork boundary in source A: rounds 1..N stay complete and the "
            "imported agent enters round N+1."
        ),
    )
    cross_run_parser.add_argument(
        "--source-b-round-end",
        dest="source_b_round_end",
        type=int,
        default=None,
        help=(
            "Last round of source B whose events feed into the imported "
            "agent's history. Defaults to min(after_round, B_max_round) "
            "so the imported agent gets all of B's history without exceeding "
            "what B actually played."
        ),
    )
    cross_run_parser.add_argument(
        "--replaced-agent-id",
        type=str,
        required=True,
        help=(
            "agent_id of the agent slot in source A to fill with the imported "
            "agent (must also exist in source B)"
        ),
    )
    cross_run_parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override the imported agent's model (defaults to source B's model)",
    )
    cross_run_parser.add_argument(
        "--provider",
        type=str,
        default=None,
        choices=[provider.value for provider in SIMULATION_PROVIDERS],
        help="Override the imported agent's provider (defaults to source B's provider)",
    )
    cross_run_parser.add_argument(
        "--runs-dir",
        type=str,
        required=True,
        help="Root directory where the new run is written",
    )
    cross_run_parser.add_argument(
        "--knobs",
        type=str,
        help=(
            "Optional scenario knob overrides: a preset name the scenario "
            "ships, or a path to a JSON file. A round_count inside it sets "
            "the fork's total rounds when --rounds-after is omitted, and "
            "must agree with it when both are given"
        ),
    )
    cross_run_parser.add_argument(
        "--visible-history-channel",
        dest="visible_history_channels",
        action="append",
        default=None,
        help=(
            "Channel ID for which the imported agent retains visibility of "
            "prior source-A messages on resume. Repeatable. When omitted, "
            "the per-channel defaults from source A's "
            "`replace_agent_default_channel_visibility` knob are used."
        ),
    )
    cross_run_parser.add_argument(
        "--rounds-after",
        dest="rounds_after",
        type=int,
        default=None,
        help=(
            "Number of new rounds the fork plays. round_count is set to "
            "after_round + rounds_after. When omitted, a round_count carried "
            "by --knobs sets the total instead, and with neither the default "
            "is source_a_round_count - after_round."
        ),
    )
    cross_run_parser.add_argument(
        "--group-slug",
        type=str,
        default=LOCAL_GROUP_SLUG,
        help=f"Tenant group slug that owns the new run (default: {LOCAL_GROUP_SLUG})",
    )


def add_fork_at_round_parser(subparsers: SubcommandParsers, scenario_names: list[str]) -> None:
    """Add the ``fork-at-round`` subcommand and its flags."""
    fork_parser = subparsers.add_parser(
        "fork-at-round",
        help=(
            "Clone a finished run keeping rounds 1..N complete and play round "
            "N+1 onward in a new run directory, without replacing any agent; "
            "every agent keeps its full reconstructed history. --rounds-after "
            "sets how far it plays, past the source's own end included; a "
            "round_count carried by --knobs does the same when the flag is "
            "omitted, and must agree with it when both are given."
        ),
    )
    fork_parser.add_argument(
        "scenario_name",
        type=str,
        choices=scenario_names,
        help="Name of the scenario the source run belongs to",
    )
    fork_parser.add_argument(
        "--source-run-dir",
        type=str,
        required=True,
        help="Path to the source run directory (e.g. runs/veyru/1742234567)",
    )
    fork_parser.add_argument(
        "--after-round",
        dest="after_round",
        type=int,
        required=True,
        help=(
            "The fork boundary: rounds 1..N stay complete, verdict and "
            "postmortem included, and the fork plays round N+1 onward."
        ),
    )
    fork_parser.add_argument(
        "--runs-dir",
        type=str,
        required=True,
        help="Root directory where the new run is written",
    )
    fork_parser.add_argument(
        "--knobs",
        type=str,
        help=(
            "Optional scenario knob overrides: a preset name the scenario "
            "ships, or a path to a JSON file. "
            "Shallow-merged onto the source's scenario_config; useful for "
            "flipping postmortem_enabled or scheduling post-hoc swaps via "
            "scheduled_events. A round_count in the payload sets the fork's "
            "total rounds when --rounds-after is omitted, and must agree "
            "with it when both are given."
        ),
    )
    fork_parser.add_argument(
        "--rounds-after",
        dest="rounds_after",
        type=int,
        default=None,
        help=(
            "Number of new rounds the fork plays. round_count is set to "
            "after_round + rounds_after. When omitted, defaults to "
            "source_round_count - after_round (the source rounds past the "
            "boundary); forking after the source's final round requires an "
            "explicit value."
        ),
    )
    fork_parser.add_argument(
        "--group-slug",
        type=str,
        default=LOCAL_GROUP_SLUG,
        help=f"Tenant group slug that owns the new run (default: {LOCAL_GROUP_SLUG})",
    )


async def _register_derived_run(
    scenario: str,
    run_dir_name: str,
    source_run_scenario: str,
    source_run_dir_name: str,
    group_slug: str,
) -> None:
    """Insert a ``runs`` row for a derived run (replace-agent / fork-at-round / cross-run).

    The detached ``glossogen run --resume`` subprocess that actually executes the
    derived simulation skips registration (it inherits the run dir from this
    parent CLI), so the parent has to register on its behalf or the FE never
    sees the run.
    """
    try:
        await register_run_standalone(
            group_slug=group_slug,
            scenario=scenario,
            run_dir_name=run_dir_name,
            status=RunStatus.STARTING.value,
            created_at=datetime.now(tz=UTC),
            created_by_user_id=None,
            source_run_scenario=source_run_scenario,
            source_run_dir_name=source_run_dir_name,
        )
    except Exception:
        logger.exception("Failed to register derived run %s/%s in Postgres", scenario, run_dir_name)


def _resolve_knob_overrides(args: argparse.Namespace) -> dict[str, Any] | None:
    """Return the `--knobs` overrides for a swap or resume flow, or None.

    Resolves a preset name as well as a path, so the flag reads the same as
    ``--config`` does on ``run``.
    """
    overrides = resolve_knobs_overrides(
        scenario_cls=get_scenario_class(name=args.scenario_name),
        requested=args.knobs,
    )
    if overrides is None:
        return None
    logger.info("Knob overrides from %s", overrides.source)
    return overrides.config


async def handle_replace_agent(args: argparse.Namespace) -> None:
    """Drive the replace-agent operation from the CLI.

    Loads optional knob overrides from ``--knobs`` and resolves the
    visible-history channel list (explicit ``--visible-history-channel``
    flags, or the source run's per-channel defaults), calls the shared
    helper, and prints the new run ID and run dir on success.
    """
    knobs = _resolve_knob_overrides(args=args)

    source_run_dir = Path(args.source_run_dir).resolve()

    if args.visible_history_channels is None:
        visible_channels = await _resolve_default_visible_channels(
            source_run_dir=source_run_dir,
            scenario_name=args.scenario_name,
            knobs=knobs,
            replaced_agent_id=args.replaced_agent_id,
            after_round=args.after_round,
        )
    else:
        visible_channels = list(args.visible_history_channels)

    if args.history_from_round is None:
        channel_history_floors: dict[str, int] = {}
    else:
        channel_history_floors = {
            channel_id: args.history_from_round for channel_id in visible_channels
        }

    logger.info(
        "Replace-agent: replaced=%s visible_channels=%s history_floors=%s history_floor_round=%s",
        args.replaced_agent_id,
        visible_channels,
        channel_history_floors,
        args.history_from_round,
    )

    request = ReplaceAgentCoreRequest(
        source_run_dir=source_run_dir,
        scenario_name=args.scenario_name,
        after_round=args.after_round,
        rounds_after=args.rounds_after,
        replaced_agent_id=args.replaced_agent_id,
        model=args.model,
        provider=args.provider,
        knobs=knobs,
        channels_with_visible_history=visible_channels,
        channel_history_floors=channel_history_floors,
        history_floor_round=args.history_from_round,
        runs_dir=Path(args.runs_dir).resolve(),
    )
    try:
        result = await replace_agent_in_run(request=request)
    except ValueError as exc:
        raise SystemExit(f"replace-agent failed: {exc}") from exc

    await _register_derived_run(
        scenario=args.scenario_name,
        run_dir_name=Path(result.new_run_dir).name,
        source_run_scenario=args.scenario_name,
        source_run_dir_name=source_run_dir.name,
        group_slug=args.group_slug,
    )
    print(f"new_run_id={result.new_run_id}")
    print(f"new_run_dir={result.new_run_dir}")


async def handle_fork_at_round(args: argparse.Namespace) -> None:
    """Drive the fork-at-round operation from the CLI.

    Loads optional knob overrides from ``--knobs`` and forwards them to
    the shared replace-agent core with ``replaced_agent_id=None`` so no
    agent is restarted. Every agent keeps its full reconstructed history
    in the fork.
    """
    knobs = _resolve_knob_overrides(args=args)

    source_run_dir = Path(args.source_run_dir).resolve()

    logger.info(
        "Fork-at-round: source=%s after_round=%d",
        source_run_dir,
        args.after_round,
    )

    request = ReplaceAgentCoreRequest(
        source_run_dir=source_run_dir,
        scenario_name=args.scenario_name,
        after_round=args.after_round,
        rounds_after=args.rounds_after,
        replaced_agent_id=None,
        model=None,
        provider=None,
        knobs=knobs,
        channels_with_visible_history=None,
        channel_history_floors={},
        history_floor_round=None,
        runs_dir=Path(args.runs_dir).resolve(),
    )
    try:
        result = await replace_agent_in_run(request=request)
    except ValueError as exc:
        raise SystemExit(f"fork-at-round failed: {exc}") from exc

    await _register_derived_run(
        scenario=args.scenario_name,
        run_dir_name=Path(result.new_run_dir).name,
        source_run_scenario=args.scenario_name,
        source_run_dir_name=source_run_dir.name,
        group_slug=args.group_slug,
    )
    print(f"new_run_id={result.new_run_id}")
    print(f"new_run_dir={result.new_run_dir}")


async def _resolve_default_visible_channels(
    source_run_dir: Path,
    scenario_name: str,
    knobs: dict[str, Any] | None,
    replaced_agent_id: str,
    after_round: int,
) -> list[str]:
    """Compute the default visible-history channel list from source-run state.

    Combines the ``replace_agent_default_channel_visibility`` knob
    (channel_id → bool) with the replaced agent's channel memberships from
    its latest ``AgentRegistered`` event, plus the direct channels created with
    it as a member in rounds up to ``after_round``, the ones the fork contains.
    The knob is read off the source run's recorded config with ``knobs``
    merged on top, validated through the scenario's knobs model: the same
    merge the fork itself validates, so a recorded config predating a required
    knob resolves once ``knobs`` supplies it. A channel is visible by default
    unless the knob explicitly maps it to ``False``.
    """
    log_path = event_log_path(run_dir=source_run_dir, scenario_name=scenario_name)
    events = await load_events(log_path=log_path)
    scenario_cls = get_scenario_class(name=scenario_name)

    visibility_map: dict[str, bool] = {}
    agent_channels: list[str] = []
    direct_channels: list[str] = []
    for event in events:
        if isinstance(event, SimulationStarted):
            visibility_map = _recorded_default_channel_visibility(
                scenario_cls=scenario_cls,
                recorded_config=event.scenario_config,
                knobs=knobs,
            )
        elif isinstance(event, AgentRegistered) and event.agent_id == replaced_agent_id:
            agent_channels = list(event.channel_ids)
        elif (
            isinstance(event, ChannelCreated)
            and replaced_agent_id in event.member_agent_ids
            and event.round_number <= after_round
        ):
            direct_channels.append(event.channel_id)

    return [
        channel_id
        for channel_id in [*agent_channels, *direct_channels]
        if visibility_map.get(channel_id, True)
    ]


def _recorded_default_channel_visibility(
    scenario_cls: type[SimulationScenario],
    recorded_config: dict[str, Any],
    knobs: dict[str, Any] | None,
) -> dict[str, bool]:
    """Return ``replace_agent_default_channel_visibility`` from a recorded config.

    ``knobs`` is merged over the recorded config before validation. Knobs the
    scenario no longer declares are dropped. A config that still does not
    validate stops the command with the validation error.
    """
    merged: dict[str, Any] = dict(recorded_config)
    if knobs is not None:
        merged.update(knobs)
    try:
        validated = scenario_cls.knobs_model().model_validate(
            scenario_cls.strip_unknown_knobs(config=merged)
        )
    except ValidationError as exc:
        logger.exception("Source run's knobs do not validate")
        raise SystemExit(
            "Cannot read replace_agent_default_channel_visibility: the source run's "
            f"config with --knobs merged does not validate ({exc}). Supply the missing "
            "knobs with --knobs, or name channels with --visible-history-channel."
        ) from exc
    return validated.replace_agent_default_channel_visibility


async def _resolve_imported_model_from_source_b(
    source_b_run_dir: Path,
    scenario_name: str,
    replaced_agent_id: str,
) -> tuple[str, str]:
    """Read source B's ``AgentRegistered`` for the replaced agent.

    Returns ``(model, provider)``. Raises ``SystemExit`` if the agent is
    missing. The orchestrator will catch the same case later, but this
    gives a clearer CLI error message.
    """
    log_path = event_log_path(run_dir=source_b_run_dir, scenario_name=scenario_name)
    events = await load_events(log_path=log_path)
    for event in events:
        if isinstance(event, AgentRegistered) and event.agent_id == replaced_agent_id:
            return event.model, event.provider
    raise SystemExit(
        f"cross-run-replace-agent: agent {replaced_agent_id!r} not found in "
        f"source B run {source_b_run_dir}"
    )


async def _resolve_source_b_max_round(source_b_run_dir: Path, scenario_name: str) -> int:
    """Return the highest ``RoundAdvanced.round_number`` observed in source B.

    Used to clamp the default ``source_b_round_end`` to source B's
    actual reach when source A's swap point is past source B's tail.
    Raises ``SystemExit`` if source B has no ``RoundAdvanced`` events.
    """
    log_path = event_log_path(run_dir=source_b_run_dir, scenario_name=scenario_name)
    events = await load_events(log_path=log_path)
    max_round = 0
    for event in events:
        if isinstance(event, RoundAdvanced) and event.round_number > max_round:
            max_round = event.round_number
    if max_round == 0:
        raise SystemExit(
            f"cross-run-replace-agent: source B run {source_b_run_dir} has no RoundAdvanced events"
        )
    return max_round


async def handle_cross_run_replace_agent(args: argparse.Namespace) -> None:
    """Drive the cross-run replace-agent operation from the CLI.

    Loads optional knob overrides from ``--knobs`` and resolves the
    visible-history channel list (explicit ``--visible-history-channel``
    flags, or source A's per-channel defaults), defaults
    ``--source-b-round-end`` to ``min(after_round, B_max_round)``
    so the imported agent gets the largest possible slice of source B's
    history without exceeding what B actually played, calls the shared
    helper, and prints the new run ID and run dir on success.
    """
    knobs = _resolve_knob_overrides(args=args)

    source_a_run_dir = Path(args.source_a_run_dir).resolve()
    source_b_run_dir = Path(args.source_b_run_dir).resolve()

    if args.visible_history_channels is None:
        visible_channels = await _resolve_default_visible_channels(
            source_run_dir=source_a_run_dir,
            scenario_name=args.scenario_name,
            knobs=knobs,
            replaced_agent_id=args.replaced_agent_id,
            after_round=args.after_round,
        )
    else:
        visible_channels = list(args.visible_history_channels)

    if args.source_b_round_end is None:
        source_b_max_round = await _resolve_source_b_max_round(
            source_b_run_dir=source_b_run_dir,
            scenario_name=args.scenario_name,
        )
        source_b_round_end = min(args.after_round, source_b_max_round)
    else:
        source_b_round_end = args.source_b_round_end

    if (args.model is None) != (args.provider is None):
        raise SystemExit(
            "cross-run-replace-agent: --model and --provider must be provided "
            "together (both or neither)"
        )
    if args.model is None:
        model, provider = await _resolve_imported_model_from_source_b(
            source_b_run_dir=source_b_run_dir,
            scenario_name=args.scenario_name,
            replaced_agent_id=args.replaced_agent_id,
        )
    else:
        model = args.model
        provider = args.provider

    logger.info(
        "Cross-run replace-agent: replaced=%s after_round=%d source_b_round_end=%d "
        "visible_channels=%s model=%s provider=%s",
        args.replaced_agent_id,
        args.after_round,
        source_b_round_end,
        visible_channels,
        model,
        provider,
    )

    request = CrossRunCoreRequest(
        source_a_run_dir=source_a_run_dir,
        source_b_run_dir=source_b_run_dir,
        scenario_name=args.scenario_name,
        after_round=args.after_round,
        source_b_round_end=source_b_round_end,
        rounds_after=args.rounds_after,
        replaced_agent_id=args.replaced_agent_id,
        model=model,
        provider=provider,
        knobs=knobs,
        channels_with_visible_history=visible_channels,
        runs_dir=Path(args.runs_dir).resolve(),
    )
    try:
        result = await cross_run_replace_agent_in_run(request=request)
    except ValueError as exc:
        raise SystemExit(f"cross-run-replace-agent failed: {exc}") from exc

    await _register_derived_run(
        scenario=args.scenario_name,
        run_dir_name=Path(result.new_run_dir).name,
        source_run_scenario=args.scenario_name,
        source_run_dir_name=source_a_run_dir.name,
        group_slug=args.group_slug,
    )
    print(f"new_run_id={result.new_run_id}")
    print(f"new_run_dir={result.new_run_dir}")
