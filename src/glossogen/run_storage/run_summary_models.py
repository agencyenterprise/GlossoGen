"""The run record a runs-directory scan returns, and the types it is made of.

:class:`RunSummary` is also the body of the runs list API, so its field names and
types are part of the server's OpenAPI schema.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel
from pydantic_ai.settings import ThinkingLevel

from glossogen.models.event import RunStatus


class ForkSource(BaseModel):
    """Provenance information for a forked simulation run."""

    source_run_id: str
    target_message_id: str
    forked_at: datetime


class ReplaceAgentSource(BaseModel):
    """Provenance for a run created via the replace-agent endpoint.

    Rounds 1..``after_round`` stay complete and the replacement agent
    enters round ``after_round + 1``. ``target_event_id`` is the resolved
    anchor inside the source run's JSONL event log, kept for traceability.
    """

    source_run_id: str
    after_round: int
    target_event_id: str
    replaced_agent_id: str
    replacement_model: str
    replacement_provider: str
    replaced_at: datetime


class ForkAtRoundSource(BaseModel):
    """Provenance for a run created via the fork-at-round endpoint.

    Rounds 1..``after_round`` stay complete and the fork plays
    ``rounds_after`` new rounds from ``after_round + 1``. No agent is
    replaced: every agent keeps its full reconstructed history, and the
    fork differs from the source only via merged knob overrides (e.g.
    ``postmortem_enabled``, ``scheduled_events``, ``round_count``).
    """

    source_run_id: str
    after_round: int
    rounds_after: int
    target_event_id: str
    forked_at: datetime


class CrossRunReplaceAgentSource(BaseModel):
    """Provenance for a run created via the cross-run replace-agent endpoint.

    ``source_a_run_id`` is the target run whose timeline was modified.
    ``source_b_run_id`` is the run the imported agent came from.
    ``source_b_round_end`` is the last Sim B round whose events fed
    into the imported agent's history.
    """

    source_a_run_id: str
    source_b_run_id: str
    after_round: int
    source_b_round_end: int
    target_event_id: str
    replaced_agent_id: str
    imported_model: str
    imported_provider: str
    replaced_at: datetime


class EvaluationScore(BaseModel):
    """One metric's overall score and one-line summary from a run's evaluation report.

    The per-round and per-agent breakdowns are left out.
    """

    metric_name: str
    score: float
    score_unit: str
    summary: str


class PlayedModel(BaseModel):
    """A model an agent played, from the round it started playing it.

    ``thinking`` is the reasoning effort its requests were sent with, ``None``
    when they left it to the provider's default or the swap that started it
    predates recorded settings.
    """

    model: str
    provider: str
    thinking: ThinkingLevel | None
    from_round: int


class AgentModelSummary(BaseModel):
    """Per-agent model and provider info for run summary display.

    ``model`` and ``provider`` are what the agent was last registered with.
    ``played`` is every model the agent played, in order, each from the round
    it started: the registered model, then each mid-run swap or replacement
    that changed it. A swap to the model and reasoning effort already playing
    adds nothing.
    """

    agent_id: str
    role_name: str
    model: str
    provider: str
    played: list[PlayedModel]


class JudgedRound(BaseModel):
    """One round the scenario judged, and whether it succeeded."""

    round_number: int
    succeeded: bool


class RoundResultTally(BaseModel):
    """How many of a team's judged rounds the scenario recorded as successful.

    ``team_id`` is None for a single-team scenario. Counts the rounds with a
    ``RoundResultRecorded`` event in the run's log, so a run still going reports
    the rounds judged so far. A round judged twice counts once, by its last
    verdict. ``rounds`` holds each judged round's verdict in round order.
    """

    team_id: str | None
    succeeded: int
    judged: int
    rounds: list[JudgedRound]


class RunSummary(BaseModel):
    """Summary of a single simulation run for the runs list endpoint.

    ``evaluation_scores`` holds every measurement in the run's evaluation report,
    in report order. It is empty when ``has_evaluation`` is false and null when
    the report exists but could not be read or parsed. ``round_results`` holds
    one tally per team the scenario judged, and is empty for a scenario that
    judges no rounds.
    """

    run_id: str
    scenario_name: str
    scenario_description: str
    scenario_config: dict[str, Any]
    timestamp: datetime
    total_messages: int
    total_cost_usd: float
    duration_seconds: float
    status: RunStatus
    has_evaluation: bool
    evaluation_scores: list[EvaluationScore] | None
    evaluation_in_progress: bool
    run_dir: str
    fork_source: ForkSource | None
    replace_agent_source: ReplaceAgentSource | None
    cross_run_replace_agent_source: CrossRunReplaceAgentSource | None
    fork_at_round_source: ForkAtRoundSource | None
    models: list[str]
    provider: str
    agent_models: list[AgentModelSummary]
    labels: list[str]
    has_note: bool
    current_round: int
    round_results: list[RoundResultTally]
    evaluation_content_hash: str | None
