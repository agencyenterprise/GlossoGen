"""Read a veyru run's JSONL once into per-agent models + per-round ground-truth context.

Shared by the baseline round-success export and the protocol-learnability export.
Walks ``agent_registered`` (per-agent model), ``veyru_case_started`` (stage ground
truth), ``veyru_stabilization_judged`` (stabilized-stage count + substage advance),
``injection_delivered`` (round-start briefings), and link-channel ``message_sent``
events, bucketing each link message into the substage active when it was sent.
"""

from pathlib import Path
from typing import NamedTuple

import orjson

from schmidt.scenarios.veyru.ids import (
    FIELD_OBSERVER_ID,
    LINK_CHANNEL_IDS,
    OBSERVER_A_ID,
    OBSERVER_B_ID,
    STABILIZATION_ENGINEER_A_ID,
    STABILIZATION_ENGINEER_B_ID,
    STABILIZATION_ENGINEER_ID,
)

FIELD_OBSERVER_IDS = frozenset({FIELD_OBSERVER_ID, OBSERVER_A_ID, OBSERVER_B_ID})
# "specialist" is a legacy agent_id some early runs used for the engineer role.
ENGINEER_IDS = frozenset(
    {
        STABILIZATION_ENGINEER_ID,
        STABILIZATION_ENGINEER_A_ID,
        STABILIZATION_ENGINEER_B_ID,
        "specialist",
    }
)


class StageGroundTruth(NamedTuple):
    """One stage's ground truth: the symptoms the observer saw and the expected procedure."""

    symptoms: str
    actions: str


class LinkMessage(NamedTuple):
    """One link-channel message: which agent sent it and the text."""

    agent: str
    message: str


class RoundContext(NamedTuple):
    """Per-round veyru ground truth and per-agent context read from the event log.

    ``stages_reached`` is the number of stages the team actually progressed to:
    ``min(stabilized_stages + 1, total_stages)`` (the team always sees stage 1, each
    stabilized stage unlocks the next, and the stage they ended on counts as reached).
    Substages beyond ``stages_reached`` are not emitted. ``stabilized_stages`` is the
    count of stages successfully stabilized this round. ``link_messages_by_substage``
    maps a 1-indexed substage to the link-channel messages exchanged while it was active.
    """

    stages: list[StageGroundTruth]
    stages_reached: int
    stabilized_stages: int
    field_observer_event: str
    engineer_event: str
    link_messages_by_substage: dict[int, list[LinkMessage]]


class RunContext(NamedTuple):
    """Per-run agent models plus per-round context, keyed by round number."""

    field_observer_model: str
    engineer_model: str
    rounds: dict[int, RoundContext]


def model_family(model: str) -> str:
    """Classify a model name as ``closed`` (claude/gpt), ``open`` (llama/qwen), or ``other``."""
    lowered = model.lower()
    if lowered.startswith(("claude", "gpt")):
        return "closed"
    if "llama" in lowered or "qwen" in lowered:
        return "open"
    return "other"


def model_class(field_observer_model: str, engineer_model: str) -> str:
    """Return ``closed`` / ``open`` / ``mixed`` from the two agents' model families.

    ``mixed`` when one agent is open-weight and the other closed (cross-family teams).
    """
    families = {model_family(field_observer_model), model_family(engineer_model)}
    families.discard("other")
    if "open" in families and "closed" in families:
        return "mixed"
    if families == {"closed"}:
        return "closed"
    if families == {"open"}:
        return "open"
    return "unknown"


def sender_role(agent_id: str) -> str:
    """Normalize a sender agent_id to ``field_observer`` or ``stabilization_engineer``.

    The engineer role appears under several ids (``stabilization_engineer``, the two-team
    ``_a`` / ``_b`` variants, and the legacy ``specialist``); they all map to
    ``stabilization_engineer``. Field observers map to ``field_observer``. Any other
    sender falls back to its raw agent_id.
    """
    if agent_id in FIELD_OBSERVER_IDS:
        return FIELD_OBSERVER_ID
    if agent_id in ENGINEER_IDS:
        return STABILIZATION_ENGINEER_ID
    return agent_id


def label_value(labels: list[str], prefix: str) -> str | None:
    """Return the suffix of the first label starting with ``prefix`` (or ``None``)."""
    for label in labels:
        if label.startswith(prefix):
            return label[len(prefix) :]
    return None


def _resolve_model(models: dict[str, str], candidate_ids: frozenset[str]) -> str:
    """Return the first registered model whose agent_id is in ``candidate_ids`` (or "")."""
    for agent_id, model in models.items():
        if agent_id in candidate_ids:
            return model
    return ""


def _injection_for(
    injections: dict[tuple[int, str], str], round_number: int, candidate_ids: frozenset[str]
) -> str:
    """Return the round-start briefing delivered to the matching agent that round (or "")."""
    for agent_id in candidate_ids:
        text = injections.get((round_number, agent_id))
        if text is not None:
            return text
    return ""


def _bucket_link_messages(
    raw_buckets: dict[int, list[LinkMessage]], stages_reached: int
) -> dict[int, list[LinkMessage]]:
    """Clamp raw per-substage message buckets into ``1..stages_reached``.

    Any messages recorded past the last reached substage (e.g. sent after the final
    stabilization of a fully-solved round) fold into ``stages_reached``, preserving
    chronological order by walking the raw substage indices in ascending order.
    """
    if stages_reached < 1:
        return {}
    clamped: dict[int, list[LinkMessage]] = {}
    for substage in sorted(raw_buckets):
        index = min(max(substage, 1), stages_reached)
        clamped.setdefault(index, []).extend(raw_buckets[substage])
    return clamped


def scan_run_context(jsonl_path: Path) -> RunContext:
    """Read a run's JSONL once and extract per-agent models + per-round veyru context.

    Tracks the most recent ``round_advanced`` to backfill ``round_number`` on older
    logs. ``stages`` come from ``veyru_case_started``; ``stabilized_stages`` from the
    count of ``veyru_stabilization_judged`` events with ``judge_match=True`` (matching
    ``outcome_reconstruction``); the round-start briefing is the first
    ``injection_delivered`` per (round, agent). Each link-channel ``message_sent`` is
    bucketed into the substage active when it was sent — a per-round counter that starts
    at 1 and advances on every ``judge_match=True`` — so messages are attributed to the
    stage the team was working on.
    """
    models: dict[str, str] = {}
    stages_by_round: dict[int, list[StageGroundTruth]] = {}
    matched_by_round: dict[int, int] = {}
    injections: dict[tuple[int, str], str] = {}
    links_by_round_substage: dict[tuple[int, int], list[LinkMessage]] = {}
    current_substage: dict[int, int] = {}
    running_round = 0
    with jsonl_path.open("rb") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            raw = orjson.loads(line)
            event_type = raw.get("event_type")
            if event_type == "round_advanced":
                advanced = raw.get("round_number")
                if isinstance(advanced, int):
                    running_round = advanced
            round_number = raw.get("round_number")
            if not isinstance(round_number, int):
                round_number = running_round
            if event_type == "agent_registered":
                agent_id = raw.get("agent_id")
                model = raw.get("model")
                if isinstance(agent_id, str) and isinstance(model, str) and agent_id not in models:
                    models[agent_id] = model
            elif event_type == "veyru_case_started" and round_number >= 1:
                stages_by_round.setdefault(
                    round_number,
                    [
                        StageGroundTruth(
                            symptoms=str(stage.get("observable_symptoms", "")),
                            actions=str(stage.get("judge_expected_actions", "")),
                        )
                        for stage in raw.get("stages", [])
                    ],
                )
            elif event_type == "veyru_stabilization_judged" and round_number >= 1:
                if raw.get("judge_match") is True:
                    matched_by_round[round_number] = matched_by_round.get(round_number, 0) + 1
                    current_substage[round_number] = current_substage.get(round_number, 1) + 1
            elif event_type == "injection_delivered" and round_number >= 1:
                agent_id = raw.get("agent_id")
                if isinstance(agent_id, str):
                    injections.setdefault((round_number, agent_id), str(raw.get("text", "")))
            elif event_type == "message_sent" and round_number >= 1:
                message = raw.get("message") or {}
                if message.get("channel_id") in LINK_CHANNEL_IDS:
                    substage = current_substage.get(round_number, 1)
                    links_by_round_substage.setdefault((round_number, substage), []).append(
                        LinkMessage(
                            agent=str(message.get("sender_agent_id", "")),
                            message=str(message.get("text", "")),
                        )
                    )
    links_grouped: dict[int, dict[int, list[LinkMessage]]] = {}
    for (round_number, substage), messages in links_by_round_substage.items():
        links_grouped.setdefault(round_number, {})[substage] = messages
    rounds: dict[int, RoundContext] = {}
    all_rounds = (
        set(stages_by_round)
        | set(matched_by_round)
        | set(links_grouped)
        | {round_number for round_number, _ in injections}
    )
    for round_number in all_rounds:
        stages = stages_by_round.get(round_number, [])
        total = len(stages)
        matched = matched_by_round.get(round_number, 0)
        stages_reached = min(matched + 1, total) if total >= 1 else 0
        rounds[round_number] = RoundContext(
            stages=stages,
            stages_reached=stages_reached,
            stabilized_stages=matched,
            field_observer_event=_injection_for(injections, round_number, FIELD_OBSERVER_IDS),
            engineer_event=_injection_for(injections, round_number, ENGINEER_IDS),
            link_messages_by_substage=_bucket_link_messages(
                raw_buckets=links_grouped.get(round_number, {}), stages_reached=stages_reached
            ),
        )
    return RunContext(
        field_observer_model=_resolve_model(models=models, candidate_ids=FIELD_OBSERVER_IDS),
        engineer_model=_resolve_model(models=models, candidate_ids=ENGINEER_IDS),
        rounds=rounds,
    )
