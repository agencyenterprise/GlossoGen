"""Building the rewind state a resumed run starts from.

One entry point, :func:`load_resume_state`, covers the three resumed shapes: a
cross-run replace-agent run (an imported agent carries another run's history), a
replace-agent or fork-at-round run (anchored at a fork boundary by its
manifest), and a plain ``--resume`` of an interrupted run (no manifest at all).

A fork whose boundary was the source's final round has no ``RoundAdvanced`` for
the round it should enter: its clone ends with the boundary round completed.
:func:`load_resume_state` detects that from the manifest (the recorded entry
round is one past the clone's last advanced round) and marks the state with
``enter_round_by_advancing`` so the supervisor advances into the entry round
instead of re-opening a finished one.

The manifest's anchor describes a pristine clone, whose last event is that
anchor. A fork that crashed after playing past its boundary has appended
events, and resuming it from the anchor would discard them and re-log the
entry round's advance. Such a run is recovered from its own last message
instead, like a plain ``--resume``, keeping the manifest's agent filters.
A progressed cross-run fork is refused: the imported agent's history is
rebuilt exclusively from source B's events, so its post-boundary turns
cannot be re-seeded.
"""

import logging
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
)
from glossogen.models.event import SimulationEvent
from glossogen.replace_manifest import read_replace_manifest
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


async def _build_cross_run_resume_state(
    events: list[SimulationEvent],
    cross_run_info: CrossRunManifestInfo,
) -> RewindState:
    """Build the rewind state for a cross-run replace-agent resume.

    Loads source B's events from ``imported_history_path``, computes
    the cutoff timestamp (Sim B's ``RoundAdvanced(source_b_round_end +
    1)`` event, or Sim B's last event when Sim B did not advance
    further), and constructs an ``AgentHistoryFilter`` that redirects
    the imported agent's history reconstruction to source B's events.
    """
    imported_events = await load_events(log_path=cross_run_info.imported_history_path)
    if cross_run_info.source_b_cutoff_event_id:
        imported_target_timestamp = next(
            event.timestamp
            for event in imported_events
            if event.event_id == cross_run_info.source_b_cutoff_event_id
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
            split_parallel_tool_calls=cross_run_info.imported_provider == SELF_HOSTED_PROVIDER,
        )
    }
    base_state = build_rewind_state_at_event(
        events=events,
        target_event_id=cross_run_info.target_event_id,
        cutoff_round=cross_run_info.entry_round,
        agent_filters=agent_filters,
    )
    return base_state._replace(
        replaced_agent_ids=frozenset({cross_run_info.replaced_agent_id}),
        replaced_agent_channel_visibility={
            cross_run_info.replaced_agent_id: cross_run_info.channel_visibility,
        },
    )


def _fork_has_progressed(
    events: list[SimulationEvent],
    target_event_id: str,
) -> bool:
    """Return whether the fork has appended events past its boundary anchor.

    A pristine clone's last event is the manifest's anchor, for both fork
    shapes: the entry round's ``RoundAdvanced``, or the last pre-end event of
    a final-round fork. Anything after it means the fork already ran.
    """
    return events[-1].event_id != target_event_id


def apply_fork_boundary(state: RewindState, entry_round: int) -> RewindState:
    """Mark the state to advance when the clone ends at a completed boundary.

    A fork whose boundary was the source's final round has no
    ``RoundAdvanced(entry_round)``: the clone's last advanced round is
    ``entry_round - 1``. The supervisor must then advance into the entry round.
    The message-count snapshot for the entry round is synthesized from the
    walked messages, because ``ChannelVisibilityFromRound(entry_round)`` on a
    replaced agent would otherwise find no snapshot and fall back to a join
    index of zero, silently granting full history.
    """
    if state.round_number == entry_round:
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
        if _fork_has_progressed(events=events, target_event_id=cross_run_info.target_event_id):
            raise ValueError(
                "this cross-run fork already played past its boundary; crash "
                "recovery cannot re-seed the imported agent's post-boundary "
                "turns, so re-create the fork with cross-run-replace-agent"
            )
        state = await _build_cross_run_resume_state(
            events=events,
            cross_run_info=cross_run_info,
        )
        logger.info(
            "Cross-run replace-agent run detected: %s resuming with full Sim B "
            "history (cutoff round=%d), channel_visibility=%s",
            cross_run_info.replaced_agent_id,
            cross_run_info.source_b_round_end,
            cross_run_info.channel_visibility,
        )
        return apply_fork_boundary(state=state, entry_round=cross_run_info.entry_round)

    replace_info = read_replace_manifest_info(run_dir=run_dir)
    if replace_info is None:
        return build_rewind_state_from_last_message(events=events, agent_filters={})

    progressed = _fork_has_progressed(
        events=events,
        target_event_id=replace_info.target_event_id,
    )
    if replace_info.replaced_agent_id is None:
        if progressed:
            logger.info(
                "Fork-at-round run already played past its boundary; "
                "recovering from its last message"
            )
            return build_rewind_state_from_last_message(events=events, agent_filters={})
        state = build_rewind_state_at_event(
            events=events,
            target_event_id=replace_info.target_event_id,
            cutoff_round=None,
            agent_filters={},
        )
        logger.info(
            "Fork-at-round run detected: entering round %d "
            "with full reconstructed history for every agent",
            replace_info.entry_round,
        )
        return apply_fork_boundary(state=state, entry_round=replace_info.entry_round)

    agent_filters = {
        replace_info.replaced_agent_id: AgentHistoryFilter(
            tool_calls_only=True,
            channel_visibility=replace_info.channel_visibility,
            imported=None,
            split_parallel_tool_calls=replace_info.replacement_provider == SELF_HOSTED_PROVIDER,
        )
    }
    if progressed:
        logger.info(
            "Replace-agent run already played past its boundary; recovering "
            "from its last message with the replaced agent still filtered"
        )
        state = build_rewind_state_from_last_message(events=events, agent_filters=agent_filters)
        return state._replace(
            replaced_agent_ids=frozenset({replace_info.replaced_agent_id}),
            replaced_agent_channel_visibility={
                replace_info.replaced_agent_id: replace_info.channel_visibility,
            },
        )
    state = build_rewind_state_at_event(
        events=events,
        target_event_id=replace_info.target_event_id,
        cutoff_round=replace_info.entry_round,
        agent_filters=agent_filters,
    )
    state = state._replace(
        replaced_agent_ids=frozenset({replace_info.replaced_agent_id}),
        replaced_agent_channel_visibility={
            replace_info.replaced_agent_id: replace_info.channel_visibility,
        },
    )
    logger.info(
        "Replace-agent run detected: %s resuming with channel_visibility=%s",
        replace_info.replaced_agent_id,
        replace_info.channel_visibility,
    )
    return apply_fork_boundary(state=state, entry_round=replace_info.entry_round)
