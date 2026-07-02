"""Read a run's JSONL once into per-role agent models + per-round ground-truth context.

Shared by the baseline round-success export, the channel-noise export, and the
protocol-learnability export. The scan is scenario-agnostic: a
:class:`ScenarioExportSpec` names the case-started / judged event types, the
primary (budgeted) channel ids, the per-stage symptom / action fields, and the
agent roles (each mapping one canonical role key to the agent ids that fill it).
Concrete specs live in :mod:`analysis.run_export.scenario_export_specs`.

Walks ``agent_registered`` (per-agent model), the case-started event (stage
ground truth), the judged event (stabilized-stage count + substage advance),
``injection_delivered`` (round-start briefings), and primary-channel
``message_sent`` events, bucketing each message into the substage active when it
was sent.
"""

from pathlib import Path
from typing import NamedTuple

import orjson


class RoleSpec(NamedTuple):
    """One export role: a canonical key, the agent ids that fill it, and its columns.

    ``role`` is the canonical key used within :class:`RunContext` / :class:`RoundContext`
    and returned by :func:`sender_role`. ``agent_ids`` are every agent id that maps to
    this role (e.g. veyru's engineer role spans the solo id, the two-team ``_a`` / ``_b``
    variants, and the legacy ``specialist``). ``model_column`` / ``event_column`` are the
    output column names the exporters emit for this role's model and round-start briefing.
    """

    role: str
    agent_ids: frozenset[str]
    model_column: str
    event_column: str


class ScenarioExportSpec(NamedTuple):
    """Everything the scan needs to read one scenario's JSONL into export context.

    ``primary_channel_ids`` are the budgeted-channel ids whose messages are bucketed
    per substage. ``case_event_type`` carries the per-round ``stages`` ground truth;
    ``stage_symptoms_field`` / ``stage_actions_field`` name the per-stage fields to read.
    ``judged_event_type`` advances the substage pointer on each ``judge_match=True``.
    ``roles`` is the ordered tuple of :class:`RoleSpec`, which drives both model
    resolution and the output column layout.
    """

    scenario_name: str
    primary_channel_ids: frozenset[str]
    case_event_type: str
    stage_symptoms_field: str
    stage_actions_field: str
    judged_event_type: str
    roles: tuple[RoleSpec, ...]


class StageGroundTruth(NamedTuple):
    """One stage's ground truth: the symptoms the actor saw and the expected procedure."""

    symptoms: str
    actions: str


class LinkMessage(NamedTuple):
    """One primary-channel message: which agent sent it, the persisted text, and its id.

    ``message`` is the text persisted on the channel — already channel-transformed
    (e.g. veyru noise drops characters to ``_``). ``message_id`` is the persisted
    message id, used to join back to the pristine pre-transform text via the
    ``send_message`` tool result.
    """

    agent: str
    message: str
    message_id: str


class RoundContext(NamedTuple):
    """Per-round ground truth and per-role context read from the event log.

    ``stages_reached`` is the number of stages the team actually progressed to:
    ``min(stabilized_stages + 1, total_stages)`` (the team always sees stage 1, each
    stabilized stage unlocks the next, and the stage they ended on counts as reached).
    Substages beyond ``stages_reached`` are not emitted. ``stabilized_stages`` is the
    count of stages successfully stabilized this round. ``role_events`` maps each role
    key to that round's round-start briefing. ``link_messages_by_substage`` maps a
    1-indexed substage to the primary-channel messages exchanged while it was active.
    """

    stages: list[StageGroundTruth]
    stages_reached: int
    stabilized_stages: int
    role_events: dict[str, str]
    link_messages_by_substage: dict[int, list[LinkMessage]]


class RunContext(NamedTuple):
    """Per-run role models plus per-round context, keyed by round number.

    ``role_models`` maps each role key (from the spec) to the model that filled it.
    """

    role_models: dict[str, str]
    rounds: dict[int, RoundContext]


def model_family(model: str) -> str:
    """Classify a model name as ``closed`` (claude/gpt), ``open`` (llama/qwen), or ``other``."""
    lowered = model.lower()
    if lowered.startswith(("claude", "gpt")):
        return "closed"
    if "llama" in lowered or "qwen" in lowered:
        return "open"
    return "other"


def model_class(role_models: dict[str, str]) -> str:
    """Return ``closed`` / ``open`` / ``mixed`` from every role's model family.

    ``mixed`` when at least one role is open-weight and at least one closed
    (cross-family teams). Roles whose family is ``other`` (or unresolved) are ignored.
    """
    families = {model_family(model) for model in role_models.values() if model}
    families.discard("other")
    if "open" in families and "closed" in families:
        return "mixed"
    if families == {"closed"}:
        return "closed"
    if families == {"open"}:
        return "open"
    return "unknown"


def sender_role(agent_id: str, spec: ScenarioExportSpec) -> str:
    """Normalize a sender agent_id to its canonical role key from ``spec``.

    Each role's ``agent_ids`` may span several ids (e.g. veyru's engineer role covers
    the solo id, the two-team ``_a`` / ``_b`` variants, and the legacy ``specialist``);
    they all map to the role key. Any sender not owned by a role falls back to its raw
    agent_id.
    """
    for role in spec.roles:
        if agent_id in role.agent_ids:
            return role.role
    return agent_id


def label_value(labels: list[str], prefix: str) -> str | None:
    """Return the suffix of the first label starting with ``prefix`` (or ``None``)."""
    for label in labels:
        if label.startswith(prefix):
            return label[len(prefix) :]
    return None


def role_model_columns(context: RunContext, spec: ScenarioExportSpec) -> dict[str, str]:
    """Return the ``{model_column: model}`` mapping for every role in ``spec``."""
    return {role.model_column: context.role_models.get(role.role, "") for role in spec.roles}


def role_event_columns(round_ctx: RoundContext, spec: ScenarioExportSpec) -> dict[str, str]:
    """Return the ``{event_column: round-start briefing}`` mapping for every role in ``spec``."""
    return {role.event_column: round_ctx.role_events.get(role.role, "") for role in spec.roles}


def model_column_names(spec: ScenarioExportSpec) -> list[str]:
    """Return the ordered per-role model column names (for stable sort keys)."""
    return [role.model_column for role in spec.roles]


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


def scan_run_context(jsonl_path: Path, spec: ScenarioExportSpec) -> RunContext:
    """Read a run's JSONL once and extract per-role models + per-round context.

    Tracks the most recent ``round_advanced`` to backfill ``round_number`` on older
    logs. ``stages`` come from the spec's case-started event; ``stabilized_stages`` from
    the count of the spec's judged events with ``judge_match=True``; the round-start
    briefing is the first ``injection_delivered`` per (round, agent). Each
    primary-channel ``message_sent`` is bucketed into the substage active when it was
    sent — a per-round counter that starts at 1 and advances on every ``judge_match=True``
    — so messages are attributed to the stage the team was working on.
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
            elif event_type == spec.case_event_type and round_number >= 1:
                stages_by_round.setdefault(
                    round_number,
                    [
                        StageGroundTruth(
                            symptoms=str(stage.get(spec.stage_symptoms_field, "")),
                            actions=str(stage.get(spec.stage_actions_field, "")),
                        )
                        for stage in raw.get("stages", [])
                    ],
                )
            elif event_type == spec.judged_event_type and round_number >= 1:
                if raw.get("judge_match") is True:
                    matched_by_round[round_number] = matched_by_round.get(round_number, 0) + 1
                    current_substage[round_number] = current_substage.get(round_number, 1) + 1
            elif event_type == "injection_delivered" and round_number >= 1:
                agent_id = raw.get("agent_id")
                if isinstance(agent_id, str):
                    injections.setdefault((round_number, agent_id), str(raw.get("text", "")))
            elif event_type == "message_sent" and round_number >= 1:
                message = raw.get("message") or {}
                if message.get("channel_id") in spec.primary_channel_ids:
                    substage = current_substage.get(round_number, 1)
                    links_by_round_substage.setdefault((round_number, substage), []).append(
                        LinkMessage(
                            agent=str(message.get("sender_agent_id", "")),
                            message=str(message.get("text", "")),
                            message_id=str(message.get("message_id", "")),
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
            role_events={
                role.role: _injection_for(injections, round_number, role.agent_ids)
                for role in spec.roles
            },
            link_messages_by_substage=_bucket_link_messages(
                raw_buckets=links_grouped.get(round_number, {}), stages_reached=stages_reached
            ),
        )
    return RunContext(
        role_models={
            role.role: _resolve_model(models=models, candidate_ids=role.agent_ids)
            for role in spec.roles
        },
        rounds=rounds,
    )
