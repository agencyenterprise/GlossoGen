"""Building the rewind state a resumed run starts from.

One entry point, :func:`load_resume_state`, covers the resumed shapes: a
cross-run replace-agent run (an imported agent carries another run's history), a
replace-agent or fork-at-round run (anchored at a fork boundary by its
manifest), and a plain ``--resume`` of an interrupted run (no manifest at all).

A fork whose boundary was the source's final round has no ``RoundAdvanced`` for
the round it should enter: its clone ends with the boundary round completed.
:func:`load_resume_state` detects that from the log itself (the last advanced
round is one behind the manifest's entry round) and marks the state with
``enter_round_by_advancing`` so the supervisor advances into the entry round
instead of re-opening a finished one.

Crash recovery classifies what the log holds past the manifest's anchor. Agent
re-registrations alone mean a launch that never got going, so the boundary
anchor still applies. Clock lifecycle events (a fresh advance, delivered
injections, a round that ended with no agent activity) are progress the anchor
would replay, so recovery re-anchors at the log's end: the state walk then
carries the already-logged advance, injections, and verdicts, and none are
recorded twice. An agent's own activity is also recovered at the log's end for
replace-agent and fork-at-round runs, with the manifest's seeding filters
bounded to the predecessor's rounds so the replacement keeps its own turns. A
cross-run fork whose imported agent may have played is refused instead: its
history is rebuilt exclusively from source B's events, so post-boundary turns
cannot be re-seeded.
"""

import logging
from enum import Enum
from pathlib import Path
from typing import NamedTuple

from glossogen.cross_run_replace_manifest import read_cross_run_replace_manifest
from glossogen.evaluation.log_reader import load_events
from glossogen.message_rewind import (
    AgentHistoryFilter,
    ImportedHistory,
    RewindState,
    build_rewind_state_at_event,
    build_rewind_state_from_last_message,
    find_event_timestamp,
)
from glossogen.models.event import (
    AgentConnected,
    AgentRegistered,
    AgentRunCycleFailed,
    AgentSwappedMidRun,
    CaseInjectedMidRun,
    ChannelHistoryCleared,
    ChannelMembershipChanged,
    InjectionDelivered,
    PostmortemDisabledMidRun,
    PostmortemEnded,
    PostmortemStarted,
    RoundAdvanced,
    RoundEnded,
    RoundResultRecorded,
    SimulationEnded,
    SimulationEvent,
    WorldEventDelivered,
)
from glossogen.replace_manifest import read_replace_manifest
from glossogen.run_archive import resume_round_from_log
from glossogen.runtime.scheduled_events import (
    ChannelVisibility,
    ChannelVisibilityFromRound,
    ChannelVisibilityFull,
    ChannelVisibilityNone,
)
from glossogen.token_pricing import SELF_HOSTED_PROVIDER

logger = logging.getLogger(__name__)


class ReplaceManifestInfo(NamedTuple):
    """Replace-agent / fork-at-round manifest fields needed at resume time.

    ``replaced_agent_id`` is ``None`` for a fork-at-round run; the resume code
    path then treats every agent as a non-replaced agent (full reconstructed
    history, no channel-visibility filtering). ``entry_round`` is the round the
    fork enters, recorded in the manifest as ``round_start``.
    """

    replaced_agent_id: str | None
    channel_visibility: dict[str, ChannelVisibility]
    target_event_id: str
    entry_round: int
    replacement_provider: str | None


class CrossRunManifestInfo(NamedTuple):
    """Cross-run replace-agent manifest fields needed to configure resume."""

    replaced_agent_id: str
    channel_visibility: dict[str, ChannelVisibility]
    target_event_id: str
    entry_round: int
    imported_history_path: Path
    source_b_round_end: int
    source_b_cutoff_event_id: str
    imported_provider: str


class ForkProgress(Enum):
    """How far past its boundary anchor a fork's log has grown."""

    PRISTINE = "pristine"
    ADVANCED = "advanced"
    PLAYED = "played"


_LAUNCH_BOOKKEEPING_EVENT_TYPES = (
    AgentRegistered,
    AgentConnected,
)

_CLOCK_LIFECYCLE_EVENT_TYPES = (
    RoundAdvanced,
    InjectionDelivered,
    RoundEnded,
    RoundResultRecorded,
    PostmortemStarted,
    PostmortemEnded,
    WorldEventDelivered,
    ChannelHistoryCleared,
    ChannelMembershipChanged,
    AgentSwappedMidRun,
    PostmortemDisabledMidRun,
    CaseInjectedMidRun,
    AgentRunCycleFailed,
    SimulationEnded,
)


def _channel_visibility_from_manifest(
    visible_channels: list[str],
    blocked_channels: list[str],
    history_floors: dict[str, int],
) -> dict[str, ChannelVisibility]:
    """Translate replace-agent manifest channel lists into a visibility dict.

    ``visible_channels`` (channels whose prior history remains visible)
    map to ``ChannelVisibilityFull``, except channels named in
    ``history_floors`` which map to ``ChannelVisibilityFromRound`` (their
    history is windowed from the floor round onward). ``blocked_channels``
    (channels whose tool calls are stripped from the predecessor's
    history) map to ``ChannelVisibilityNone``. Channels not in any list
    are omitted (caller decides default behaviour).
    """
    result: dict[str, ChannelVisibility] = {}
    for channel_id in visible_channels:
        floor = history_floors.get(channel_id)
        if floor is None:
            result[channel_id] = ChannelVisibilityFull()
        else:
            result[channel_id] = ChannelVisibilityFromRound(round_floor=floor)
    for channel_id in blocked_channels:
        result[channel_id] = ChannelVisibilityNone()
    return result


def read_replace_manifest_info(run_dir: Path) -> ReplaceManifestInfo | None:
    """Read ``replace_manifest.json`` if present and project to resume fields."""
    manifest = read_replace_manifest(run_dir=run_dir)
    if manifest is None:
        return None
    return ReplaceManifestInfo(
        replaced_agent_id=manifest.replaced_agent_id,
        channel_visibility=_channel_visibility_from_manifest(
            visible_channels=list(manifest.channels_with_visible_history),
            blocked_channels=list(manifest.blocked_tool_call_channels),
            history_floors=dict(manifest.channel_history_floors),
        ),
        target_event_id=manifest.target_event_id,
        entry_round=manifest.round_start,
        replacement_provider=manifest.replacement_provider,
    )


def read_cross_run_manifest_info(run_dir: Path) -> CrossRunManifestInfo | None:
    """Read ``cross_run_replace_manifest.json`` if present and project to resume fields."""
    manifest = read_cross_run_replace_manifest(run_dir=run_dir)
    if manifest is None:
        return None
    return CrossRunManifestInfo(
        replaced_agent_id=manifest.replaced_agent_id,
        channel_visibility=_channel_visibility_from_manifest(
            visible_channels=list(manifest.channels_with_visible_history),
            blocked_channels=list(manifest.blocked_tool_call_channels),
            history_floors={},
        ),
        target_event_id=manifest.target_event_id,
        entry_round=manifest.round_start,
        imported_history_path=run_dir / manifest.imported_history_source,
        source_b_round_end=manifest.source_b_round_end,
        source_b_cutoff_event_id=manifest.source_b_cutoff_event_id,
        imported_provider=manifest.imported_provider,
    )


def classify_fork_progress(
    events: list[SimulationEvent],
    target_event_id: str,
) -> ForkProgress:
    """Classify what the fork's log holds past its boundary anchor.

    A launch appends agent re-registrations before anything happens, so those
    alone still mean a first launch (``PRISTINE``). Clock lifecycle events
    mean the clock made progress a boundary-anchored rebuild would replay
    (``ADVANCED``). Anything else is an agent's own activity (``PLAYED``);
    an event type this function does not know counts as played, so the
    classification fails closed.
    """
    anchor_seen = False
    progress = ForkProgress.PRISTINE
    for event in events:
        if anchor_seen:
            if isinstance(event, _LAUNCH_BOOKKEEPING_EVENT_TYPES):
                continue
            if isinstance(event, _CLOCK_LIFECYCLE_EVENT_TYPES):
                progress = ForkProgress.ADVANCED
                continue
            return ForkProgress.PLAYED
        if event.event_id == target_event_id:
            anchor_seen = True
    return progress


def apply_fork_boundary(state: RewindState, entry_round: int) -> RewindState:
    """Mark the state to advance when the clone ends at a completed boundary.

    A fork whose boundary was the source's final round has no
    ``RoundAdvanced(entry_round)``: the clone's last advanced round is
    ``entry_round - 1``. The supervisor must then advance into the entry round.
    A state at or past the entry round needs no advance; recovery of a fork
    that already logged its fresh ``RoundAdvanced`` lands here, which is what
    keeps the advance from being recorded twice.
    The message-count snapshot for the entry round is synthesized from the
    walked messages, because ``ChannelVisibilityFromRound(entry_round)`` on a
    replaced agent would otherwise find no snapshot and fall back to a join
    index of zero, silently granting full history.
    """
    if state.round_number >= entry_round:
        return state
    if state.round_number != entry_round - 1:
        raise ValueError(
            f"clone is inconsistent with its manifest: last advanced round is "
            f"{state.round_number} but the manifest enters round {entry_round}"
        )
    snapshot = dict(state.channel_message_count_at_round_start)
    snapshot[entry_round] = {
        channel_id: len(messages) for channel_id, messages in state.messages_by_channel.items()
    }
    return state._replace(
        enter_round_by_advancing=True,
        channel_message_count_at_round_start=snapshot,
    )


def _mark_replaced(
    state: RewindState,
    agent_id: str,
    channel_visibility: dict[str, ChannelVisibility],
) -> RewindState:
    """Record which agent was replaced and how its channel view is reconfigured."""
    return state._replace(
        replaced_agent_ids=frozenset({agent_id}),
        replaced_agent_channel_visibility={agent_id: channel_visibility},
    )


def _resume_anchor_event_id(
    events: list[SimulationEvent],
    target_event_id: str,
    progress: ForkProgress,
) -> str:
    """Pick where the rebuilt state anchors: the boundary, or the log's end.

    A pristine clone anchors at the manifest's boundary event. A clone that
    grew past it anchors at its own last event, so the state walk carries
    every advance, injection, and verdict the previous launch already logged
    and none are recorded twice.
    """
    if progress is ForkProgress.PRISTINE:
        return target_event_id
    return events[-1].event_id


async def _build_cross_run_resume_state(
    events: list[SimulationEvent],
    cross_run_info: CrossRunManifestInfo,
    anchor_event_id: str,
    cutoff_round: int | None,
) -> RewindState:
    """Build the rewind state for a cross-run replace-agent resume.

    Loads source B's events from ``imported_history_path``, computes
    the cutoff timestamp (Sim B's ``RoundAdvanced(source_b_round_end +
    1)`` event, or Sim B's last event when Sim B did not advance
    further), and constructs an ``AgentHistoryFilter`` that redirects
    the imported agent's history reconstruction to source B's events.
    """
    imported_events = await load_events(log_path=cross_run_info.imported_history_path)
    if not imported_events:
        raise ValueError(
            f"imported history at {cross_run_info.imported_history_path} holds no events"
        )
    if cross_run_info.source_b_cutoff_event_id:
        imported_target_timestamp = find_event_timestamp(
            events=imported_events,
            target_event_id=cross_run_info.source_b_cutoff_event_id,
        )
    else:
        imported_target_timestamp = imported_events[-1].timestamp

    agent_filters: dict[str, AgentHistoryFilter] = {
        cross_run_info.replaced_agent_id: AgentHistoryFilter(
            tool_calls_only=False,
            channel_visibility=cross_run_info.channel_visibility,
            imported=ImportedHistory(
                events=tuple(imported_events),
                target_timestamp=imported_target_timestamp,
                cutoff_round=cross_run_info.source_b_round_end + 1,
            ),
            filter_below_round=None,
            split_parallel_tool_calls=cross_run_info.imported_provider == SELF_HOSTED_PROVIDER,
        )
    }
    base_state = build_rewind_state_at_event(
        events=events,
        target_event_id=anchor_event_id,
        cutoff_round=cutoff_round,
        agent_filters=agent_filters,
    )
    return _mark_replaced(
        state=base_state,
        agent_id=cross_run_info.replaced_agent_id,
        channel_visibility=cross_run_info.channel_visibility,
    )


async def _load_cross_run_state(
    events: list[SimulationEvent],
    cross_run_info: CrossRunManifestInfo,
) -> RewindState:
    """Resume a cross-run replace-agent run, refusing the unrecoverable shape."""
    progress = classify_fork_progress(
        events=events,
        target_event_id=cross_run_info.target_event_id,
    )
    if progress is ForkProgress.PLAYED:
        raise ValueError(
            "this cross-run fork already played past its boundary; crash "
            "recovery cannot re-seed the imported agent's post-boundary "
            "turns, so re-create the fork with cross-run-replace-agent"
        )
    if progress is ForkProgress.PRISTINE:
        cutoff_round: int | None = cross_run_info.entry_round
    else:
        cutoff_round = None
        logger.info("Cross-run fork crashed after clock bookkeeping; recovering at the log's end")
    state = await _build_cross_run_resume_state(
        events=events,
        cross_run_info=cross_run_info,
        anchor_event_id=_resume_anchor_event_id(
            events=events,
            target_event_id=cross_run_info.target_event_id,
            progress=progress,
        ),
        cutoff_round=cutoff_round,
    )
    logger.info(
        "Cross-run replace-agent run detected: %s resuming with full Sim B "
        "history (cutoff round=%d), channel_visibility=%s",
        cross_run_info.replaced_agent_id,
        cross_run_info.source_b_round_end,
        cross_run_info.channel_visibility,
    )
    return apply_fork_boundary(state=state, entry_round=cross_run_info.entry_round)


def _load_fork_at_round_state(
    events: list[SimulationEvent],
    replace_info: ReplaceManifestInfo,
) -> RewindState:
    """Resume a fork-at-round run, from its boundary or from where it crashed."""
    progress = classify_fork_progress(
        events=events,
        target_event_id=replace_info.target_event_id,
    )
    if progress is ForkProgress.PRISTINE:
        logger.info(
            "Fork-at-round run detected: entering round %d "
            "with full reconstructed history for every agent",
            replace_info.entry_round,
        )
    else:
        logger.info("Fork-at-round run grew past its boundary; recovering at the log's end")
    state = build_rewind_state_at_event(
        events=events,
        target_event_id=_resume_anchor_event_id(
            events=events,
            target_event_id=replace_info.target_event_id,
            progress=progress,
        ),
        cutoff_round=None,
        agent_filters={},
    )
    return apply_fork_boundary(state=state, entry_round=replace_info.entry_round)


def _load_replace_agent_state(
    events: list[SimulationEvent],
    replace_info: ReplaceManifestInfo,
    replaced_agent_id: str,
) -> RewindState:
    """Resume a replace-agent run, keeping the replaced seat's seeding filters.

    The filters are bounded to the rounds before the fork's entry round, so
    crash recovery strips only the predecessor's turns: the replacement's own
    post-boundary text, thinking, and channel traffic stay in its history.
    """
    progress = classify_fork_progress(
        events=events,
        target_event_id=replace_info.target_event_id,
    )
    agent_filters = {
        replaced_agent_id: AgentHistoryFilter(
            tool_calls_only=True,
            channel_visibility=replace_info.channel_visibility,
            imported=None,
            filter_below_round=replace_info.entry_round,
            split_parallel_tool_calls=replace_info.replacement_provider == SELF_HOSTED_PROVIDER,
        )
    }
    if progress is ForkProgress.PRISTINE:
        cutoff_round: int | None = replace_info.entry_round
        logger.info(
            "Replace-agent run detected: %s resuming with channel_visibility=%s",
            replaced_agent_id,
            replace_info.channel_visibility,
        )
    else:
        cutoff_round = None
        logger.info(
            "Replace-agent run grew past its boundary; recovering at the "
            "log's end with the replaced agent's predecessor still filtered"
        )
    state = build_rewind_state_at_event(
        events=events,
        target_event_id=_resume_anchor_event_id(
            events=events,
            target_event_id=replace_info.target_event_id,
            progress=progress,
        ),
        cutoff_round=cutoff_round,
        agent_filters=agent_filters,
    )
    state = _mark_replaced(
        state=state,
        agent_id=replaced_agent_id,
        channel_visibility=replace_info.channel_visibility,
    )
    return apply_fork_boundary(state=state, entry_round=replace_info.entry_round)


async def load_resume_state(
    run_dir: Path,
    events: list[SimulationEvent],
) -> RewindState:
    """Build the rewind state for a resumed run from its directory and events.

    Dispatches on the manifests in ``run_dir``: cross-run replace-agent, then
    replace-agent / fork-at-round, then plain ``--resume`` with no manifest.
    """
    cross_run_info = read_cross_run_manifest_info(run_dir=run_dir)
    if cross_run_info is not None:
        return await _load_cross_run_state(events=events, cross_run_info=cross_run_info)

    replace_info = read_replace_manifest_info(run_dir=run_dir)
    if replace_info is None:
        return build_rewind_state_from_last_message(events=events, agent_filters={})

    if replace_info.replaced_agent_id is None:
        return _load_fork_at_round_state(events=events, replace_info=replace_info)
    return _load_replace_agent_state(
        events=events,
        replace_info=replace_info,
        replaced_agent_id=replace_info.replaced_agent_id,
    )


def resume_first_round(resume_dir: Path | None, scenario_name: str) -> int:
    """Return the round this launch will open at, which fresh runs answer with 1.

    A resumed run inherits its source's schedule, and the boundaries below where
    it opens are ones the clock will never cross. The run's own log answers for
    a plain ``--resume``; a fork past the source's final round holds no
    ``RoundAdvanced`` for its entry round, so the manifest's entry round wins
    when it is higher. This is the preflight's projection of the decision
    :func:`load_resume_state` makes with the full event log in hand; the two
    live side by side so a change to one is a change to both.
    """
    if resume_dir is None:
        return 1
    first_round = resume_round_from_log(log_path=resume_dir / f"{scenario_name}.jsonl")
    replace_info = read_replace_manifest_info(run_dir=resume_dir)
    if replace_info is not None:
        first_round = max(first_round, replace_info.entry_round)
    cross_info = read_cross_run_manifest_info(run_dir=resume_dir)
    if cross_info is not None:
        first_round = max(first_round, cross_info.entry_round)
    return first_round
