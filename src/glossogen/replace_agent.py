"""Core implementation of the replace-agent and fork-at-round operations.

Used by the ``glossogen replace-agent`` and ``glossogen fork-at-round`` CLI
subcommands. Locates the fork boundary in the source run's JSONL, copies the
run directory with the log truncated at that boundary, writes a manifest, and
launches a resumed subprocess.

The boundary is the *end* of round ``after_round``: the fork keeps rounds
``1..after_round`` complete, verdict and postmortem included, and plays round
``after_round + 1`` onward. When the source finished at ``after_round`` itself
(no later round exists), the clone is truncated before ``SimulationEnded`` and
the resumed clock advances into the new round instead of re-opening one.

When ``replaced_agent_id`` is set, that agent restarts fresh while every other
agent keeps its full reconstructed history. When ``replaced_agent_id`` is
``None`` (fork-at-round), every agent keeps its full reconstructed history;
only the JSONL clone, knob merge, and round-count adjustment happen.
"""

import logging
import sys
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple, cast

import orjson

from glossogen.cross_run_replace_manifest import CROSS_RUN_REPLACE_MANIFEST_FILENAME
from glossogen.evaluation.log_reader import load_events
from glossogen.message_rewind import build_rewind_state_at_event
from glossogen.models.event import (
    AgentRegistered,
    RoundAdvanced,
    RoundEnded,
    RunStatus,
    SimulationEnded,
    SimulationEvent,
    SimulationStarted,
)
from glossogen.provider_credentials import require_reachable_models
from glossogen.replace_manifest import REPLACE_MANIFEST_FILENAME, ReplaceManifest
from glossogen.run_archive import claim_run_dir, copy_run_at_event, find_event_offset
from glossogen.run_config_validation import validate_run_config
from glossogen.run_jsonl_rewriter import (
    drop_simulation_ended,
    patch_simulation_started_scenario_config,
    rewrite_run_jsonl,
)
from glossogen.run_launching import PreparedForkRun, launch_prepared_run
from glossogen.scenario_loader import get_scenario_class
from glossogen.token_pricing import list_providers

logger = logging.getLogger(__name__)


class ReplaceAgentRequest(NamedTuple):
    """Input parameters for a replace-agent or fork-at-round operation.

    The boundary is the *end* of round ``after_round``: the fork keeps that
    round's verdict and postmortem and plays round ``after_round + 1`` onward.
    The exact event that anchors the truncation is resolved internally.

    ``rounds_after`` is how many new rounds the fork plays: round_count is set
    to ``after_round + rounds_after``. When ``None``, it defaults to
    ``source_round_count - after_round`` (the source rounds past the boundary);
    forking after the source's final round therefore requires an explicit
    value.

    When ``replaced_agent_id`` is set, that agent restarts with only the
    prior agent's tool-call history (text and thinking stripped, blocked
    channels dropped) and runs under ``model``/``provider``; every other
    agent keeps its full reconstructed history pinned to its
    source-active model.

    When ``replaced_agent_id`` is ``None``, the operation is a pure
    fork-at-round: ``model``, ``provider``, and
    ``channels_with_visible_history`` must also be ``None``, every agent
    keeps its full reconstructed history pinned to its source-active
    model, and knob overrides are the only behavioural change.
    """

    source_run_dir: Path
    scenario_name: str
    after_round: int
    rounds_after: int | None
    replaced_agent_id: str | None
    model: str | None
    provider: str | None
    knobs: dict[str, Any] | None
    channels_with_visible_history: list[str] | None
    channel_history_floors: dict[str, int]
    runs_dir: Path


class ReplaceAgentResult(NamedTuple):
    """Result of a successful replace-agent launch."""

    new_run_id: str
    new_run_dir: Path


class ForkBoundary(NamedTuple):
    """Where a fork cuts the source log.

    ``target_event_id`` is the last event the clone keeps. When the source
    played rounds past the boundary, that is the ``RoundAdvanced`` for the
    entry round and the resumed clock re-opens it. When the boundary round was
    the source's last, ``advances_into_round`` is ``True``: the clone ends just
    before ``SimulationEnded`` and the resumed clock must advance into the
    entry round with a fresh ``RoundAdvanced``.
    """

    target_event_id: str
    boundary_timestamp: datetime
    advances_into_round: bool


def compose_run_id(scenario_name: str, run_dir_name: str) -> str:
    """Build the canonical ``<scenario>/<run_dir>`` identifier."""
    return f"{scenario_name}/{run_dir_name}"


def resolve_fork_boundary(
    events: list[SimulationEvent],
    after_round: int,
) -> ForkBoundary:
    """Resolve where the clone's JSONL is truncated for a fork after ``after_round``.

    When the source advanced into round ``after_round + 1``, that
    ``RoundAdvanced`` is the anchor: the clone captures round ``after_round``
    fully closed, with the entry round opened but its injections not yet
    delivered, and the resumed clock re-opens it. When the source *finished* at
    round ``after_round``, the anchor is the last event before
    ``SimulationEnded``, and the resumed clock advances into the entry round
    instead.

    Raises ``ValueError`` when ``after_round`` is below 1, when the source
    never completed that round, when the source opened it but never finished
    it, or when the source's last end marker is not ``scenario_complete``: a
    killed or errored source may have stopped mid-round, so its final round
    is not a completed boundary. A ``scenario_complete`` end can also land
    mid-round, through a scenario's ``is_finished_early`` hook, so the
    boundary round must additionally carry its ``RoundEnded``; logs recorded
    before that event existed carry none anywhere and skip the check.
    """
    if after_round < 1:
        raise ValueError(
            "--after-round must be >= 1: a fork keeps rounds 1..N and plays "
            "round N+1 onward; to replay from the beginning, launch a fresh run"
        )
    entry_round = after_round + 1
    last_advanced_round = 0
    log_has_round_ended_events = False
    boundary_round_ended = False
    for event in events:
        if isinstance(event, RoundEnded):
            log_has_round_ended_events = True
            if event.round_number == after_round:
                boundary_round_ended = True
        if isinstance(event, RoundAdvanced):
            last_advanced_round = max(last_advanced_round, event.round_number)
            if event.round_number == entry_round:
                return ForkBoundary(
                    target_event_id=event.event_id,
                    boundary_timestamp=event.timestamp,
                    advances_into_round=False,
                )
    if last_advanced_round < after_round:
        raise ValueError(
            f"source run never completed round {after_round}: "
            f"last round advanced was {last_advanced_round}"
        )
    last_ended: SimulationEnded | None = None
    target: SimulationEvent | None = None
    for event in reversed(events):
        if isinstance(event, SimulationEnded):
            if last_ended is None:
                last_ended = event
        elif target is None:
            target = event
        if last_ended is not None and target is not None:
            break
    if last_ended is None:
        raise ValueError(
            f"source run opened round {after_round} but never finished it "
            f"(no simulation_ended); fork-at-round requires a completed boundary"
        )
    if last_ended.reason != RunStatus.SCENARIO_COMPLETE:
        raise ValueError(
            f"source run ended with reason {last_ended.reason.value!r}, so round "
            f"{after_round} may be incomplete; fork after the last round the "
            f"source completed instead"
        )
    if log_has_round_ended_events and not boundary_round_ended:
        raise ValueError(
            f"source run ended scenario_complete without closing round "
            f"{after_round} (no round_ended for it), so that round was never "
            f"judged; fork after the last round the source completed instead"
        )
    if target is None:
        raise ValueError("source run holds nothing before simulation_ended")
    return ForkBoundary(
        target_event_id=target.event_id,
        boundary_timestamp=target.timestamp,
        advances_into_round=True,
    )


def _manifest_replaced_agent_id(manifest_path: Path) -> str | None:
    """Read ``replaced_agent_id`` from a manifest file, tolerating every era's shape."""
    raw = orjson.loads(manifest_path.read_bytes())
    if not isinstance(raw, dict):
        return None
    seat = cast(dict[str, Any], raw).get("replaced_agent_id")
    if isinstance(seat, str):
        return seat
    return None


def refuse_unforkable_source(
    source_run_dir: Path,
    replaced_agent_id: str | None,
) -> None:
    """Refuse a source whose log cannot rebuild every seat the fork rebuilds pass-through.

    A cross-run source's log holds the replaced-away agent's turns before its
    import boundary. A replace-agent source's log holds the predecessor's
    turns before its swap, and the filters that hid them live only in the
    source's manifest, which clones do not inherit. Either way, a seat rebuilt
    pass-through from the clone would remember turns its live agent never
    saw. Replacing the same seat again is allowed: the new replacement's
    filters cover that seat's whole prior history.
    """
    if (source_run_dir / CROSS_RUN_REPLACE_MANIFEST_FILENAME).exists():
        raise ValueError(
            f"source run {source_run_dir} is a cross-run replace-agent "
            "run; forking it is not supported because the imported agent's "
            "history cannot be rebuilt past its import boundary"
        )
    manifest_path = source_run_dir / REPLACE_MANIFEST_FILENAME
    if not manifest_path.exists():
        return
    source_seat = _manifest_replaced_agent_id(manifest_path=manifest_path)
    if source_seat is None or source_seat == replaced_agent_id:
        return
    raise ValueError(
        f"source run {source_run_dir} is a replace-agent run: its log holds "
        f"the predecessor's unfiltered turns for seat {source_seat!r}, and the "
        "filters that hid them live only in the source's manifest, which the "
        "clone does not inherit. Fork the source's own source instead, or "
        f"replace the same agent ({source_seat!r}) again"
    )


def refuse_source_b_with_mixed_seat(
    source_b_run_dir: Path,
    imported_agent_id: str,
) -> None:
    """Refuse importing a seat whose source-B log mixes two agents' turns.

    When source B was itself created by replacing or importing that same
    seat, its log holds the replaced-away agent's turns before B's own
    boundary, and the imported agent's real earlier context lives in B's own
    import sidecar, which this flow never reads. Importing a different seat
    from such a run is fine: that seat's turns in B's log are all its own.
    """
    for manifest_filename, flow_name in (
        (CROSS_RUN_REPLACE_MANIFEST_FILENAME, "cross-run replace-agent"),
        (REPLACE_MANIFEST_FILENAME, "replace-agent"),
    ):
        manifest_path = source_b_run_dir / manifest_filename
        if not manifest_path.exists():
            continue
        source_seat = _manifest_replaced_agent_id(manifest_path=manifest_path)
        if source_seat != imported_agent_id:
            continue
        raise ValueError(
            f"source B run {source_b_run_dir} is a {flow_name} run whose own "
            f"boundary replaced {imported_agent_id!r}: its log holds the "
            "replaced-away agent's turns before that boundary, so importing "
            "that seat would mix two agents' histories. Import it from the "
            "run the agent originally played in"
        )


def collect_source_agents(
    events: list[SimulationEvent],
    boundary_timestamp: datetime,
) -> dict[str, AgentRegistered]:
    """Return each agent's latest ``AgentRegistered`` at the fork boundary.

    Filters to events whose timestamp is at or before
    ``boundary_timestamp`` so forking a multi-swap source picks up each
    agent's model/system_prompt as it was at the chosen boundary, not
    a later in-run swap registration that overwrote it.
    """
    out: dict[str, AgentRegistered] = {}
    for event in events:
        if event.timestamp > boundary_timestamp:
            break
        if isinstance(event, AgentRegistered):
            out[event.agent_id] = event
    return out


def build_model_overrides(
    source_agents: dict[str, AgentRegistered],
    replaced_agent_id: str | None,
    replacement_model: str | None,
    replacement_provider: str | None,
    user_overrides: dict[str, dict[str, str]] | None,
) -> dict[str, dict[str, str]]:
    """Pin every source agent to its source-active model, with user overrides on top.

    Encoding every agent explicitly (rather than relying on the top-level
    ``--model``/``--provider`` defaults) keeps non-replaced agents on
    their exact source-active models. Layering ``user_overrides`` on top
    lets the fork caller pin specific agents to a different model (e.g.
    haiku for cheap smoke tests) without losing the source-pin for the
    remaining agents. When ``replaced_agent_id`` is set, the agent's entry
    is forced to ``replacement_model``/``replacement_provider`` last so
    the replacement payload always wins over the user-provided knob entry.
    """
    overrides: dict[str, dict[str, str]] = {}
    for agent_id, registration in source_agents.items():
        overrides[agent_id] = {
            "model": registration.model,
            "provider": registration.provider,
        }
    if user_overrides is not None:
        for agent_id, override in user_overrides.items():
            if agent_id not in overrides:
                # Pre-validation happens later; reject unknown agent IDs early
                # so the user gets a clear error rather than a silently ignored entry.
                raise ValueError(
                    f"model_overrides references unknown agent_id={agent_id!r}; "
                    f"known agents in source: {sorted(overrides)}"
                )
            overrides[agent_id] = {
                "model": override["model"],
                "provider": override["provider"],
            }
    if replaced_agent_id is not None:
        if replacement_model is None or replacement_provider is None:
            raise ValueError(
                "replacement_model and replacement_provider are required when "
                "replaced_agent_id is set"
            )
        overrides[replaced_agent_id] = {
            "model": replacement_model,
            "provider": replacement_provider,
        }
    return overrides


def _validate_replacement_payload(request: ReplaceAgentRequest) -> None:
    """Enforce the request's ``replaced_agent_id`` invariant before any I/O.

    When ``replaced_agent_id`` is set, ``model``, ``provider``, and
    ``channels_with_visible_history`` must all be present and ``provider``
    must be a known provider name. When ``replaced_agent_id`` is ``None``,
    all three companion fields must also be ``None`` and
    ``channel_history_floors`` must be empty so the fork-at-round code path
    has no half-populated replacement state to interpret.

    Every channel named in ``channel_history_floors`` must also appear in
    ``channels_with_visible_history`` (a windowed channel is still a
    visible channel), and each floor must satisfy
    ``1 <= floor <= after_round + 1`` (a floor of the entry round yields zero
    prior history, the no-history window).
    """
    if request.replaced_agent_id is None:
        misset = [
            field
            for field, value in (
                ("model", request.model),
                ("provider", request.provider),
                ("channels_with_visible_history", request.channels_with_visible_history),
            )
            if value is not None
        ]
        if request.channel_history_floors:
            misset.append("channel_history_floors")
        if misset:
            raise ValueError(
                f"replaced_agent_id is None but {', '.join(misset)} is set; "
                "fork-at-round requires all replacement fields to be None"
            )
        return
    missing = [
        field
        for field, value in (
            ("model", request.model),
            ("provider", request.provider),
            ("channels_with_visible_history", request.channels_with_visible_history),
        )
        if value is None
    ]
    if missing:
        raise ValueError(
            f"replaced_agent_id is set but {', '.join(missing)} is missing; "
            "replace-agent requires all replacement fields to be provided"
        )
    if request.provider not in list_providers():
        raise ValueError(f"Unknown provider: {request.provider}")
    entry_round = request.after_round + 1
    visible = set(request.channels_with_visible_history or [])
    for channel_id, floor in request.channel_history_floors.items():
        if channel_id not in visible:
            raise ValueError(
                f"channel_history_floors names channel {channel_id!r} which is not in "
                f"channels_with_visible_history; a windowed channel must also be visible"
            )
        if not 1 <= floor <= entry_round:
            raise ValueError(
                f"channel_history_floors[{channel_id!r}]={floor} must satisfy "
                f"1 <= floor <= after_round + 1 ({entry_round})"
            )


def _pick_subprocess_default_model(
    request: ReplaceAgentRequest,
    source_agents: dict[str, AgentRegistered],
) -> tuple[str, str]:
    """Return the ``--model`` / ``--provider`` pair to launch the resumed subprocess with.

    For replace-agent runs we forward the caller's replacement model so
    the subprocess's ``run`` defaults match the replacement. For
    fork-at-round runs no agent uses the defaults (every agent is pinned via
    ``model_overrides``) but ``glossogen run`` still requires the flags; we
    pick the first source agent's registration arbitrarily.
    """
    if request.model is not None and request.provider is not None:
        return request.model, request.provider
    first_registration = next(iter(source_agents.values()), None)
    if first_registration is None:
        raise ValueError("Source run has no AgentRegistered events; cannot pick default model")
    return first_registration.model, first_registration.provider


def resolve_rounds_after(
    after_round: int,
    rounds_after: int | None,
    knob_round_count: int | None,
    source_scenario_config: Mapping[str, Any],
) -> int:
    """Return the stored manifest window, ``round_count - entry_round``.

    An explicit ``rounds_after`` of K plays rounds
    ``after_round + 1 .. after_round + K`` and stores ``K - 1``.
    ``knob_round_count`` is a ``round_count`` the caller's ``--knobs`` carry
    (every shipped preset does): it sets the fork's total rounds when
    ``rounds_after`` is omitted, and must agree with it when both are given.
    With neither, the default replays the source rounds past the boundary;
    forking after the source's final round has no such rounds, so it needs
    one of the explicit forms.
    """
    if rounds_after is not None:
        if rounds_after < 1:
            raise ValueError("--rounds-after must be >= 1: the fork must play at least one round")
        if knob_round_count is not None and knob_round_count != after_round + rounds_after:
            raise ValueError(
                f"--rounds-after {rounds_after} and the --knobs round_count "
                f"{knob_round_count} disagree: after_round {after_round} + "
                f"rounds_after {rounds_after} = {after_round + rounds_after}; "
                f"drop one of them"
            )
        return rounds_after - 1
    if knob_round_count is not None:
        stored_window = knob_round_count - (after_round + 1)
        if stored_window < 0:
            raise ValueError(
                f"the --knobs round_count {knob_round_count} leaves no rounds "
                f"past --after-round {after_round}; the fork must play at "
                f"least one round"
            )
        return stored_window
    source_round_count = source_scenario_config.get("round_count")
    if not isinstance(source_round_count, int):
        raise ValueError(
            "Cannot derive default rounds_after: source run's "
            "scenario_config has no integer 'round_count' entry"
        )
    entry_round = after_round + 1
    stored_window = source_round_count - entry_round
    if stored_window < 0:
        raise ValueError(
            f"source run ends at round {source_round_count}; "
            f"--after-round {after_round} leaves no source rounds to "
            f"replay, so pass an explicit --rounds-after"
        )
    return stored_window


def resolve_knob_round_count(knobs: dict[str, Any] | None) -> int | None:
    """Return the integer ``round_count`` a knob payload carries, if any.

    A non-integer value is refused here rather than surfacing later as a
    schema validation error against a config whose ``round_count`` this flow
    computes itself.
    """
    if knobs is None or "round_count" not in knobs:
        return None
    value = knobs["round_count"]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"--knobs round_count must be an integer, got {value!r}")
    return value


async def prepare_replace_agent_run(request: ReplaceAgentRequest) -> PreparedForkRun:
    """Prepare a replace-agent or fork-at-round run on disk, without launching it.

    Everything up to and including the manifest write: boundary resolution,
    clone with truncated JSONL, config merge and validation, credential
    preflight. Raises ``ValueError`` for caller-fixable errors (unknown
    provider / scenario / agent / inconsistent ``replaced_agent_id`` payload)
    so the CLI layer can surface a clear message without re-implementing
    validation.
    """
    _validate_replacement_payload(request=request)
    # Raises with the installed scenario names before any file is touched.
    get_scenario_class(name=request.scenario_name)

    refuse_unforkable_source(
        source_run_dir=request.source_run_dir,
        replaced_agent_id=request.replaced_agent_id,
    )

    source_log_path = request.source_run_dir / f"{request.scenario_name}.jsonl"
    if not source_log_path.exists():
        raise ValueError(f"Source run JSONL not found: {source_log_path}")

    source_events = await load_events(log_path=source_log_path)

    boundary = resolve_fork_boundary(
        events=source_events,
        after_round=request.after_round,
    )
    entry_round = request.after_round + 1
    if boundary.advances_into_round:
        logger.info(
            "Fork boundary is the source's final round: the resumed clock will "
            "advance into round %d, which the source never played",
            entry_round,
        )
    source_agents = collect_source_agents(
        events=source_events,
        boundary_timestamp=boundary.boundary_timestamp,
    )
    if request.replaced_agent_id is not None and request.replaced_agent_id not in source_agents:
        raise ValueError(
            f"Agent {request.replaced_agent_id!r} not found in source run "
            f"as of the end of round {request.after_round} "
            f"(known agents: {sorted(source_agents)})"
        )

    location = await find_event_offset(
        log_path=source_log_path,
        event_id=boundary.target_event_id,
    )
    if location is None:
        raise ValueError(
            f"No event {boundary.target_event_id} "
            f"(fork boundary after round {request.after_round}) "
            f"found in {source_log_path}"
        )

    source_first_event = source_events[0]
    if not isinstance(source_first_event, SimulationStarted):
        raise ValueError("First event in source JSONL is not SimulationStarted")

    scenario_cls = get_scenario_class(name=request.scenario_name)

    merged_scenario_config: dict[str, Any] = dict(source_first_event.scenario_config)
    if request.knobs is not None:
        merged_scenario_config.update(request.knobs)
    effective_rounds_after_swap = resolve_rounds_after(
        after_round=request.after_round,
        rounds_after=request.rounds_after,
        knob_round_count=resolve_knob_round_count(knobs=request.knobs),
        source_scenario_config=source_first_event.scenario_config,
    )
    merged_scenario_config["round_count"] = entry_round + effective_rounds_after_swap
    # Extract any user-provided model_overrides from the merged knobs so they
    # survive the source-agent pinning that follows. Anything not specified by
    # the user falls back to the source-active model.
    raw_user_overrides = merged_scenario_config.get("model_overrides")
    user_overrides: dict[str, dict[str, str]] | None = None
    if isinstance(raw_user_overrides, dict):
        coerced: dict[str, dict[str, str]] = {}
        for agent_id, value in cast(dict[Any, Any], raw_user_overrides).items():
            if not isinstance(value, dict) or "model" not in value or "provider" not in value:
                raise ValueError(
                    f"model_overrides[{agent_id!r}] must be an object with "
                    "'model' and 'provider' string fields"
                )
            typed_value = cast(dict[str, Any], value)
            coerced[str(agent_id)] = {
                "model": str(typed_value["model"]),
                "provider": str(typed_value["provider"]),
            }
        user_overrides = coerced
    merged_scenario_config["model_overrides"] = build_model_overrides(
        source_agents=source_agents,
        replaced_agent_id=request.replaced_agent_id,
        replacement_model=request.model,
        replacement_provider=request.provider,
        user_overrides=user_overrides,
    )

    subprocess_model, subprocess_provider = _pick_subprocess_default_model(
        request=request,
        source_agents=source_agents,
    )
    validated = validate_run_config(
        scenario_cls=scenario_cls,
        scenario_config=merged_scenario_config,
        default_provider=subprocess_provider,
        valid_providers=set(list_providers()),
    )

    require_reachable_models(
        scenario_cls=scenario_cls,
        scenario_config=validated.scenario_config,
        agent_overrides=validated.normalized_agent_overrides,
        default_model=subprocess_model,
        default_provider=subprocess_provider,
        first_round=entry_round,
    )

    new_run_dir = claim_run_dir(
        runs_dir=request.runs_dir,
        scenario_name=request.scenario_name,
    )
    new_log_filename = f"{request.scenario_name}.jsonl"
    await copy_run_at_event(
        source_dir=request.source_run_dir,
        target_dir=new_run_dir,
        jsonl_path_within_run=Path(new_log_filename),
        truncate_after_offset=location.end_offset,
    )

    new_run_id = compose_run_id(
        scenario_name=request.scenario_name,
        run_dir_name=new_run_dir.name,
    )
    new_log_path = new_run_dir / new_log_filename

    rewrite_run_jsonl(
        log_path=new_log_path,
        new_run_id=new_run_id,
        message_edits={},
        should_drop_event=drop_simulation_ended,
    )

    rewritten_events = await load_events(log_path=new_log_path)
    build_rewind_state_at_event(
        events=rewritten_events,
        target_event_id=boundary.target_event_id,
        cutoff_round=entry_round,
        agent_filters={},
    )

    config_path = new_run_dir / "replace_config.json"
    config_path.write_bytes(orjson.dumps(validated.scenario_config))

    patch_simulation_started_scenario_config(
        log_path=new_log_path,
        scenario_config=validated.scenario_config,
    )

    source_run_id = compose_run_id(
        scenario_name=request.scenario_name,
        run_dir_name=request.source_run_dir.name,
    )
    if request.replaced_agent_id is None:
        blocked_tool_call_channels: list[str] = []
        visible_channels: list[str] = []
    else:
        blocked_tool_call_channels = sorted(
            scenario_cls.get_replace_agent_blocked_tool_call_channels()
        )
        assert request.channels_with_visible_history is not None
        visible_channels = list(request.channels_with_visible_history)
    manifest = ReplaceManifest(
        source_run_id=source_run_id,
        source_run_dir=str(request.source_run_dir),
        round_start=entry_round,
        rounds_after_swap=effective_rounds_after_swap,
        target_event_id=boundary.target_event_id,
        replaced_agent_id=request.replaced_agent_id,
        replacement_model=request.model,
        replacement_provider=request.provider,
        channels_with_visible_history=visible_channels,
        blocked_tool_call_channels=blocked_tool_call_channels,
        channel_history_floors=dict(request.channel_history_floors),
        replaced_at=time.time(),
    )
    manifest_path = new_run_dir / REPLACE_MANIFEST_FILENAME
    manifest_path.write_bytes(orjson.dumps(manifest.model_dump()))

    stdout_log = new_run_dir / f"{request.scenario_name}_stdout.log"
    cmd = (
        sys.executable,
        "-m",
        "glossogen",
        "run",
        request.scenario_name,
        "--model",
        subprocess_model,
        "--provider",
        subprocess_provider,
        "--resume",
        str(new_run_dir),
        "--config",
        str(config_path),
    )
    return PreparedForkRun(
        new_run_id=new_run_id,
        new_run_dir=new_run_dir,
        launch_cmd=cmd,
        stdout_log_path=stdout_log,
    )


async def replace_agent_in_run(request: ReplaceAgentRequest) -> ReplaceAgentResult:
    """Prepare and launch a replace-agent or fork-at-round run.

    The resumed subprocess is spawned detached as a side-effect; see
    :func:`prepare_replace_agent_run` for everything that happens before the
    launch.
    """
    prepared = await prepare_replace_agent_run(request=request)
    logger.info("Launching forked simulation: %s", " ".join(prepared.launch_cmd))
    launch_prepared_run(prepared=prepared)
    return ReplaceAgentResult(new_run_id=prepared.new_run_id, new_run_dir=prepared.new_run_dir)
