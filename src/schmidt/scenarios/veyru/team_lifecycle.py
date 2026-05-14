"""Mid-simulation team transitions: observer swap and intern join/takeover.

The world owns the *state mutations* (`swap_observers`,
`promote_intern_to_observer`); this module owns the *side-effect
choreography* that has to happen at the same round boundary —
updating channel membership lists, clearing channel histories, sending
the announcement messages, and toggling the postmortem channel when
the swap closes it. All three transitions are gated by the round
number against the relevant knob.
"""

import logging

from schmidt.runtime.scenario_world import WorldContext
from schmidt.scenarios.veyru.ids import (
    FIELD_OBSERVER_ID,
    INTERN_ID,
    INTERN_JOIN_REASON,
    INTERN_TAKEOVER_REASON,
    LINK_CHANNEL_ID,
    OBSERVER_SWAP_REASON,
    POSTMORTEM_CHANNEL_ID,
    STABILIZATION_ENGINEER_ID,
    TEAM_A_ID,
    TEAM_B_ID,
)
from schmidt.scenarios.veyru.knobs import VeyruKnobs
from schmidt.scenarios.veyru.world import VeyruWorld

logger = logging.getLogger(__name__)


async def maybe_swap_observers(world: VeyruWorld, knobs: VeyruKnobs, round_number: int) -> None:
    """Swap observers, clear channel histories, announce, and toggle postmortem.

    Veyru-style: the swap fires at the start of the round AFTER the
    configured ``swap_round`` so that round number completes before
    the observers exchange. No-op in single-team mode or before the
    boundary.
    """
    if knobs.swap_round is None:
        return
    if round_number != knobs.swap_round + 1:
        return

    new_team_a_observer, new_team_b_observer = world.swap_observers()
    logger.info(
        "Veyru observer swap fired at round %d: team A observer=%s, team B observer=%s",
        round_number,
        new_team_a_observer,
        new_team_b_observer,
    )

    team_a = world.teams[TEAM_A_ID]
    team_b = world.teams[TEAM_B_ID]
    context = world.context

    await _apply_swap_to_channel(
        context=context,
        channel_id=team_a.link_channel_id,
        observer_id=team_a.current_observer_id,
        stabilization_engineer_id=team_a.stabilization_engineer_id,
    )
    await _apply_swap_to_channel(
        context=context,
        channel_id=team_b.link_channel_id,
        observer_id=team_b.current_observer_id,
        stabilization_engineer_id=team_b.stabilization_engineer_id,
    )
    if team_a.postmortem_channel_id is not None:
        await _apply_swap_to_channel(
            context=context,
            channel_id=team_a.postmortem_channel_id,
            observer_id=team_a.current_observer_id,
            stabilization_engineer_id=team_a.stabilization_engineer_id,
        )
    if team_b.postmortem_channel_id is not None:
        await _apply_swap_to_channel(
            context=context,
            channel_id=team_b.postmortem_channel_id,
            observer_id=team_b.current_observer_id,
            stabilization_engineer_id=team_b.stabilization_engineer_id,
        )

    if knobs.announce_swap:
        world.mark_swap_just_happened()
        announcement = (
            "=== TEAM RECONFIGURATION ===\n"
            "The field observers between the two teams have been swapped. "
            "The channel history has been cleared."
        )
        await context.send_update_to_channel(
            channel_id=team_a.link_channel_id,
            text=announcement,
        )
        await context.send_update_to_channel(
            channel_id=team_b.link_channel_id,
            text=announcement,
        )

    if knobs.postmortem_enabled and not knobs.postmortem_after_swap:
        world.disable_postmortem_globally()


async def maybe_join_intern(world: VeyruWorld, knobs: VeyruKnobs, round_number: int) -> None:
    """At ``intern_join_round``, add the intern to the link channel and announce."""
    if knobs.intern_join_round is None:
        return
    if round_number != knobs.intern_join_round:
        return

    logger.info("Intern joining link channel at round %d", round_number)
    context = world.context
    await context.update_channel_members(
        channel_id=LINK_CHANNEL_ID,
        member_agent_ids=[FIELD_OBSERVER_ID, STABILIZATION_ENGINEER_ID, INTERN_ID],
        reason=INTERN_JOIN_REASON,
    )
    await context.send_update_to_channel(
        channel_id=LINK_CHANNEL_ID,
        text=(
            "An intern observer has joined the comm link and will silently "
            "observe your work. They will not speak or act until further notice."
        ),
    )


async def maybe_promote_intern(world: VeyruWorld, knobs: VeyruKnobs, round_number: int) -> None:
    """At ``intern_takeover_round``, replace the field observer with the intern."""
    if knobs.intern_takeover_round is None:
        return
    if round_number != knobs.intern_takeover_round:
        return

    displaced = world.promote_intern_to_observer(intern_id=INTERN_ID)
    logger.info(
        "Intern takeover fired at round %d: displaced observer=%s",
        round_number,
        displaced,
    )

    context = world.context
    await context.update_channel_members(
        channel_id=LINK_CHANNEL_ID,
        member_agent_ids=[STABILIZATION_ENGINEER_ID, INTERN_ID],
        reason=INTERN_TAKEOVER_REASON,
    )
    if knobs.postmortem_enabled:
        if knobs.postmortem_after_swap:
            await context.update_channel_members(
                channel_id=POSTMORTEM_CHANNEL_ID,
                member_agent_ids=[STABILIZATION_ENGINEER_ID, INTERN_ID],
                reason=INTERN_TAKEOVER_REASON,
            )
        else:
            world.disable_postmortem_globally()

    await context.send_update_to_channel(
        channel_id=LINK_CHANNEL_ID,
        text=(
            "=== FIELD OBSERVER HANDOFF ===\n"
            "The intern has taken over as the active field observer. "
            "The previous field observer has left the comm link. "
            "Continue the protocol with the new pairing."
        ),
    )


async def _apply_swap_to_channel(
    context: WorldContext,
    channel_id: str,
    observer_id: str,
    stabilization_engineer_id: str,
) -> None:
    """Apply membership update + history wipe to one channel as part of a swap."""
    await context.update_channel_members(
        channel_id=channel_id,
        member_agent_ids=[observer_id, stabilization_engineer_id],
        reason=OBSERVER_SWAP_REASON,
    )
    await context.clear_channel_history(
        channel_id=channel_id,
        reason=OBSERVER_SWAP_REASON,
    )
