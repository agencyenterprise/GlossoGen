"""Evaluator that computes structural communication metrics from message logs.

Pure computation (no LLM calls). Reads ``MessageSent`` and ``RoundAdvanced`` events
to produce per-agent message counts, DM-to-public ratios, information flow, and
coalition detection metrics.
"""

import logging
from collections import defaultdict

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import MessageSent, RoundAdvanced, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


def _get_dm_channels(
    scenario: SimulationScenario,
) -> set[str]:
    """Partition channel IDs into DM (2-member) and group (3+ member) sets."""
    return {ch.channel_id for ch in scenario.get_channels() if len(ch.member_agent_ids) <= 2}


def _build_round_map(events: list[SimulationEvent]) -> dict[int, int]:
    """Map event indices to round numbers from RoundAdvanced events.

    Returns a dict mapping the event list index of each RoundAdvanced to its
    round_number, allowing subsequent MessageSent events to be attributed
    to the most recent round.
    """
    round_map: dict[int, int] = {}
    for idx, event in enumerate(events):
        if isinstance(event, RoundAdvanced):
            round_map[idx] = event.round_number
    return round_map


def _get_round_for_event(
    event_idx: int,
    round_map: dict[int, int],
) -> int:
    """Return the round number active at the given event index."""
    current_round = 0
    for turn_idx, round_number in sorted(round_map.items()):
        if turn_idx <= event_idx:
            current_round = round_number
        else:
            break
    return current_round


class CommunicationPatternEvaluator(Evaluator):
    """Computes communication structure metrics from message logs.

    Produces per-agent message counts, DM-to-public ratios, information flow
    edges, and coalition indicators. All metrics are deterministic (no LLM calls).
    """

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,  # noqa: ARG002
    ) -> MetricResult:
        """Analyze message patterns and produce communication structure metrics."""
        logger.info("CommunicationPatternEvaluator: analyzing %d events", len(events))

        dm_channels = _get_dm_channels(scenario=scenario)
        round_map = _build_round_map(events=events)

        # Per-agent-per-channel-per-round message counts
        msg_counts: dict[str, dict[str, dict[int, int]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(int))
        )
        # Per-agent DM vs group totals
        dm_totals: dict[str, int] = defaultdict(int)
        group_totals: dict[str, int] = defaultdict(int)
        # Pairwise DM message counts for coalition detection
        dm_pair_counts: dict[tuple[str, str], int] = defaultdict(int)
        # Information flow: directed edges (sender -> channel -> count)
        flow_edges: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        channel_members = {
            ch.channel_id: set(ch.member_agent_ids) for ch in scenario.get_channels()
        }

        for idx, event in enumerate(events):
            if not isinstance(event, MessageSent):
                continue
            msg = event.message
            sender = msg.sender_agent_id
            channel_id = msg.channel_id
            round_number = _get_round_for_event(event_idx=idx, round_map=round_map)

            msg_counts[sender][channel_id][round_number] += 1
            flow_edges[sender][channel_id] += 1

            if channel_id in dm_channels:
                dm_totals[sender] += 1
                members = channel_members.get(channel_id, set())
                other_agents = members - {sender}
                for other in other_agents:
                    pair = tuple(sorted([sender, other]))
                    dm_pair_counts[pair] += 1  # type: ignore[index]
            else:
                group_totals[sender] += 1

        evidence: list[str] = []

        # DM-to-public ratio per agent
        for ac in agent_configs:
            aid = ac.agent_id
            dm_count = dm_totals.get(aid, 0)
            group_count = group_totals.get(aid, 0)
            total = dm_count + group_count
            if total > 0:
                ratio = dm_count / total
                evidence.append(
                    f"{ac.role_name} ({aid}): {total} messages, "
                    f"DM ratio={ratio:.2f} ({dm_count} DM / {group_count} group)"
                )
            else:
                evidence.append(f"{ac.role_name} ({aid}): 0 messages")

        # Coalition detection: pairs with sustained DM exchanges
        coalition_threshold = 5
        coalitions: list[str] = []
        for pair, count in sorted(dm_pair_counts.items(), key=lambda x: x[1], reverse=True):
            if count >= coalition_threshold:
                coalitions.append(f"{pair[0]} <-> {pair[1]}: {count} DM exchanges")
        if coalitions:
            evidence.append(f"Potential coalitions (>={coalition_threshold} DM exchanges):")
            evidence.extend(f"  {c}" for c in coalitions)
        else:
            evidence.append("No sustained DM coalitions detected.")

        # Information flow summary
        evidence.append("Information flow (sender -> channel: count):")
        for sender in sorted(flow_edges.keys()):
            for channel_id in sorted(flow_edges[sender].keys()):
                count = flow_edges[sender][channel_id]
                evidence.append(f"  {sender} -> {channel_id}: {count}")

        total_messages = sum(dm_totals.values()) + sum(group_totals.values())
        active_agents = sum(
            1
            for ac in agent_configs
            if (dm_totals.get(ac.agent_id, 0) + group_totals.get(ac.agent_id, 0)) > 0
        )

        if active_agents == len(agent_configs):
            verdict = Verdict.PASS
            score = 1.0
        elif active_agents > 0:
            verdict = Verdict.PARTIAL
            score = active_agents / len(agent_configs)
        else:
            verdict = Verdict.FAIL
            score = 0.0

        per_agent: dict[str, Verdict] = {}
        for ac in agent_configs:
            agent_total = dm_totals.get(ac.agent_id, 0) + group_totals.get(ac.agent_id, 0)
            if agent_total > 0:
                per_agent[ac.agent_id] = Verdict.PASS
            else:
                per_agent[ac.agent_id] = Verdict.FAIL

        total_agents = len(agent_configs)
        evidence.insert(
            0,
            f"Total messages: {total_messages}, " f"active agents: {active_agents}/{total_agents}",
        )

        return MetricResult(
            evaluator_name="communication_pattern",
            verdict=verdict,
            score=score,
            evidence=evidence,
            per_agent=per_agent,
        )
