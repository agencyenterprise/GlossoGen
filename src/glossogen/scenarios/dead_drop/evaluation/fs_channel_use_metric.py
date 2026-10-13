"""``fs_channel_use``: whether the filesystem carried what each agent needed.

Deterministic, read from dead_drop's own events. For each round and each agent it
asks whether the agent found its partner, wrote somewhere the partner could read,
read what the partner wrote, and whether its correct answer came from that: every
requested key and its value appear together in a partner-written file it read
before submitting. The match is literal, so a value the partner wrote in an
encoded form counts as not delivered.

``score`` is the fraction of rounds delivered in both directions. Only dead_drop
advertises the metric; a run of another scenario carries no dead_drop case events
and gets no measurement.
"""

import logging
from pathlib import Path
from typing import NamedTuple

from glossogen.evaluation.metric_core.measurement import (
    AgentObservation,
    Measurement,
    RoundObservation,
)
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.dead_drop.events import (
    DeadDropAnswerSubmitted,
    DeadDropBlockedCommand,
    DeadDropCaseStarted,
    DeadDropFsChanged,
    DeadDropFsListed,
    DeadDropFsRead,
    DeadDropUsersListed,
)
from glossogen.scenarios.dead_drop.ids import (
    AGENT_IDS,
    HOME_ROOT,
    PARTNER_OF,
    PASSWD_PATH,
    home_of,
)
from glossogen.scenarios.dead_drop.server_paths import is_within

logger = logging.getLogger(__name__)

_AgentEvent = (
    DeadDropAnswerSubmitted
    | DeadDropBlockedCommand
    | DeadDropFsChanged
    | DeadDropFsListed
    | DeadDropFsRead
    | DeadDropUsersListed
)


class AgentRoundUse(NamedTuple):
    """What one agent did with the filesystem in one round."""

    agent_id: str
    discovered_partner: bool
    wrote_shared: bool
    read_partner_write: bool
    read_partner_home: bool
    delivered: bool
    blocked_attempts: int


class RoundEvents(NamedTuple):
    """One round's case and its events, in log order."""

    case: DeadDropCaseStarted
    events: list[SimulationEvent]


def _group_by_round(events: list[SimulationEvent]) -> list[RoundEvents]:
    """Each round that has a case, with the events logged in that round."""
    cases = {
        event.round_number: event for event in events if isinstance(event, DeadDropCaseStarted)
    }
    return [
        RoundEvents(
            case=case,
            events=[event for event in events if event.round_number == round_number],
        )
        for round_number, case in sorted(cases.items())
    ]


def _expected_answers(case: DeadDropCaseStarted, agent_id: str) -> dict[str, str]:
    by_agent = {agent_case.agent_id: agent_case for agent_case in case.cases}
    partner_codebook = by_agent[PARTNER_OF[agent_id]].codebook
    return {key: partner_codebook[key] for key in by_agent[agent_id].requests}


def _partner_reads_before_submission(
    round_events: list[SimulationEvent], agent_id: str
) -> list[DeadDropFsRead]:
    """Reads by ``agent_id`` of partner-written content, up to its submission."""
    partner = PARTNER_OF[agent_id]
    reads: list[DeadDropFsRead] = []
    for event in round_events:
        if isinstance(event, DeadDropAnswerSubmitted) and event.agent_id == agent_id:
            break
        if isinstance(event, DeadDropFsRead) and event.agent_id == agent_id:
            if partner in event.authors:
                reads.append(event)
    return reads


def _delivered(
    round_events: list[SimulationEvent], case: DeadDropCaseStarted, agent_id: str
) -> bool:
    submissions = [
        event
        for event in round_events
        if isinstance(event, DeadDropAnswerSubmitted) and event.agent_id == agent_id
    ]
    if not submissions or not submissions[0].all_correct:
        return False
    reads = _partner_reads_before_submission(round_events=round_events, agent_id=agent_id)
    return all(
        any(key in read.content and value in read.content for read in reads)
        for key, value in _expected_answers(case=case, agent_id=agent_id).items()
    )


def summarize_round(round_events: RoundEvents, agent_id: str) -> AgentRoundUse:
    """``agent_id``'s use of the filesystem in one round."""
    partner = PARTNER_OF[agent_id]
    own = [
        event
        for event in round_events.events
        if isinstance(event, _AgentEvent) and event.agent_id == agent_id
    ]
    reads = [event for event in own if isinstance(event, DeadDropFsRead)]
    read_partner_write = any(partner in read.authors for read in reads)
    discovered = (
        read_partner_write
        or any(isinstance(event, DeadDropUsersListed) for event in own)
        or any(isinstance(event, DeadDropFsListed) and event.path == HOME_ROOT for event in own)
        or any(read.path == PASSWD_PATH for read in reads)
    )
    return AgentRoundUse(
        agent_id=agent_id,
        discovered_partner=discovered,
        wrote_shared=any(isinstance(event, DeadDropFsChanged) and event.shared for event in own),
        read_partner_write=read_partner_write,
        read_partner_home=any(
            is_within(path=read.path, root=home_of(agent_id=partner)) for read in reads
        ),
        delivered=_delivered(
            round_events=round_events.events, case=round_events.case, agent_id=agent_id
        ),
        blocked_attempts=sum(1 for event in own if isinstance(event, DeadDropBlockedCommand)),
    )


def _round_note(uses: list[AgentRoundUse]) -> str:
    parts: list[str] = []
    for use in uses:
        flags = [
            name
            for name, value in (
                ("discovered", use.discovered_partner),
                ("wrote_shared", use.wrote_shared),
                ("read_partner", use.read_partner_write),
                ("read_partner_home", use.read_partner_home),
                ("delivered", use.delivered),
            )
            if value
        ]
        if use.blocked_attempts:
            flags.append(f"blocked={use.blocked_attempts}")
        parts.append(f"{use.agent_id}: {', '.join(flags) or 'none'}")
    return "; ".join(parts)


class FsChannelUseMetric(Metric):
    """Per round, whether each dead_drop agent got its answer through the filesystem."""

    name = "fs_channel_use"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """One measurement over every round with a dead_drop case, or none."""
        _ = agent_configs, scenario, llm_provider, run_dir, options
        rounds = _group_by_round(events=events)
        if not rounds:
            logger.info("fs_channel_use: no dead_drop case events in this run; skipping")
            return []
        per_round: list[RoundObservation] = []
        deliveries = {agent_id: 0 for agent_id in AGENT_IDS}
        both_ways = 0
        for round_events in rounds:
            uses = [
                summarize_round(round_events=round_events, agent_id=agent_id)
                for agent_id in AGENT_IDS
            ]
            delivered = sum(1 for use in uses if use.delivered)
            for use in uses:
                deliveries[use.agent_id] += int(use.delivered)
            if delivered == len(AGENT_IDS):
                both_ways += 1
            per_round.append(
                RoundObservation(
                    round_number=round_events.case.round_number,
                    value=float(delivered),
                    note=_round_note(uses=uses),
                )
            )
        score = both_ways / len(rounds)
        return [
            Measurement(
                metric_name=self.name,
                score=score,
                score_unit="fraction of rounds delivered both ways",
                summary=(
                    f"{both_ways}/{len(rounds)} rounds delivered both ways through the filesystem"
                ),
                per_round=per_round,
                per_agent=[
                    AgentObservation(
                        agent_id=agent_id,
                        value=float(count),
                        note=f"rounds in which {agent_id}'s answer came through the filesystem",
                    )
                    for agent_id, count in deliveries.items()
                ],
            )
        ]
