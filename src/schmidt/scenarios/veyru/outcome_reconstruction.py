"""Build ``VeyruOutcome`` records from live state or from a JSONL event log.

Two entry points share the same ``VeyruOutcome`` shape:

* :func:`compute_outcome_if_needed` reads the current ``TeamState`` and
  builds an outcome on demand — used by postmortem injections, which run
  *before* the next round's reset clears the team's per-round counters.
* :func:`restore_outcomes_from_events` walks a JSONL event list on
  resume / fork / replace-agent and appends one ``VeyruOutcome`` per
  completed round per team. Without it the round-N injection right
  after resume would render a blank "previous round" block.
"""

from schmidt.scenarios.veyru.ids import TeamId
from schmidt.scenarios.veyru.veyru_cases import VeyruCase
from schmidt.scenarios.veyru.world_state import StageOutcome, TeamState, VeyruOutcome


def compute_outcome_if_needed(
    teams: dict[TeamId, TeamState],
    veyru_cases: list[VeyruCase],
    round_number: int,
    team_id: TeamId,
    case_overrides: dict[int, VeyruCase],
) -> VeyruOutcome | None:
    """Compute and store the outcome for ``team_id`` / ``round_number`` if not already done.

    Returns the outcome, or ``None`` when ``round_number < 1``. Idempotent:
    if an outcome for this round was already appended, returns it without
    appending a duplicate. ``case_overrides`` provides per-round case
    overrides set by ``InjectCase`` scheduled events — when ``round_number``
    has an override, the outcome's ``failure_name`` / ``stages`` / budget
    reflect the injected case rather than the natural-cycle pick.
    """
    if round_number < 1:
        return None
    team = teams[team_id]
    for existing in team.outcomes:
        if existing.case_number == round_number:
            return existing
    override = case_overrides.get(round_number)
    if override is not None:
        case = override
    else:
        case_index = (round_number - 1) % len(veyru_cases)
        case = veyru_cases[case_index]
    all_stage_outcomes = list(team.stage_outcomes)
    for i in range(len(all_stage_outcomes), len(case.stages)):
        all_stage_outcomes.append(
            StageOutcome(
                motif_name=case.stages[i].motif_name,
                stabilized=False,
            )
        )
    outcome = VeyruOutcome(
        team_id=team_id,
        case_number=round_number,
        failure_name=case.failure_name,
        stabilized=team.veyru_stabilized,
        characters_used=team.current_round_characters,
        time_elapsed_seconds=team.current_round_characters,
        time_budget_seconds=case.time_budget_seconds,
        stages_completed=len(team.stage_outcomes),
        total_stages=len(case.stages),
        stage_outcomes=tuple(all_stage_outcomes),
    )
    team.outcomes.append(outcome)
    return outcome


def restore_outcomes_from_events(
    teams: dict[TeamId, TeamState],
    veyru_cases: list[VeyruCase],
    channels_by_team: dict[str, TeamId],
    events: list[object],
) -> None:
    """Seed per-team ``outcomes`` from a JSONL event list.

    Walks the events once, groups per-round/per-team data from
    ``message_sent`` (character totals on link channels),
    ``veyru_stabilization_judged`` (per-team stages stabilized), and
    ``round_ended`` (which rounds completed and how), then appends one
    ``VeyruOutcome`` per completed round per team.
    """
    characters_by_round_team: dict[int, dict[TeamId, int]] = {}
    matched_stages_by_round_team: dict[int, dict[TeamId, int]] = {}
    round_ended_trigger: dict[int, str] = {}
    for event in events:
        event_type = getattr(event, "event_type", None)
        round_number = getattr(event, "round_number", None)
        if not isinstance(round_number, int) or round_number < 1:
            continue
        if event_type == "message_sent":
            message = getattr(event, "message", None)
            channel_id = getattr(message, "channel_id", None)
            text = getattr(message, "text", "")
            if isinstance(channel_id, str) and channel_id in channels_by_team:
                team_id = channels_by_team[channel_id]
                bucket = characters_by_round_team.setdefault(round_number, {})
                bucket[team_id] = bucket.get(team_id, 0) + len(text)
        elif event_type == "veyru_stabilization_judged":
            if not getattr(event, "judge_match", False):
                continue
            agent_id = getattr(event, "agent_id", "")
            if not isinstance(agent_id, str):
                continue
            resolved_team_id = _team_for_agent_id_lookup(teams=teams, agent_id=agent_id)
            if resolved_team_id is None:
                continue
            bucket = matched_stages_by_round_team.setdefault(round_number, {})
            bucket[resolved_team_id] = bucket.get(resolved_team_id, 0) + 1
        elif event_type == "round_ended":
            trigger = getattr(event, "trigger", None)
            if isinstance(trigger, str):
                round_ended_trigger[round_number] = trigger

    for round_number in sorted(round_ended_trigger.keys()):
        trigger = round_ended_trigger[round_number]
        case_index = (round_number - 1) % len(veyru_cases)
        case = veyru_cases[case_index]
        stabilized_round = trigger == "veyru_stabilized"
        chars_for_round = characters_by_round_team.get(round_number, {})
        matched_for_round = matched_stages_by_round_team.get(round_number, {})
        for team_id, team in teams.items():
            if any(o.case_number == round_number for o in team.outcomes):
                continue
            chars = chars_for_round.get(team_id, 0)
            matched = matched_for_round.get(team_id, 0)
            stage_outcomes = tuple(
                StageOutcome(
                    motif_name=case.stages[i].motif_name,
                    stabilized=i < matched,
                )
                for i in range(len(case.stages))
            )
            team.outcomes.append(
                VeyruOutcome(
                    team_id=team_id,
                    case_number=round_number,
                    failure_name=case.failure_name,
                    stabilized=stabilized_round and matched >= len(case.stages),
                    characters_used=chars,
                    time_elapsed_seconds=chars,
                    time_budget_seconds=case.time_budget_seconds,
                    stages_completed=matched,
                    total_stages=len(case.stages),
                    stage_outcomes=stage_outcomes,
                )
            )


def _team_for_agent_id_lookup(teams: dict[TeamId, TeamState], agent_id: str) -> TeamId | None:
    """Return the team whose observer or engineer is ``agent_id``, or None."""
    for team_id, state in teams.items():
        if state.current_observer_id == agent_id:
            return team_id
        if state.stabilization_engineer_id == agent_id:
            return team_id
    return None
