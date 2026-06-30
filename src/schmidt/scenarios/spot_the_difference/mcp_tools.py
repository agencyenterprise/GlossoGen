"""The single MCP tool the spot_the_difference scenario exposes to its agents.

``submit_differences`` is a viewer's one action: submit the team's free-text
list of the differences between the two scenes. When ``all_must_submit`` is off
the first call from either member locks the team's answer for the round; when it
is on, each member submits their own answer and the team locks only once both
have submitted. Once the team is complete an LLM judge scores every submitted
answer, the combined verdict is recorded, and a JSONL event is written per
answer. The result is not revealed at submit time — it is announced when the
round ends — so the submission stays one-shot.
"""

from typing import Callable

from schmidt.llm.provider import LLMProvider
from schmidt.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from schmidt.scenario_protocol import ScenarioRuntimeHandle
from schmidt.scenarios.spot_the_difference.difference_judge import (
    combine_team_verdict,
    judge_submission,
)
from schmidt.scenarios.spot_the_difference.events import DifferenceSubmissionJudged
from schmidt.scenarios.spot_the_difference.ids import (
    ALREADY_SUBMITTED_MARKER,
    SUBMISSION_RECORDED_MARKER,
    SUBMISSION_WAITING_MARKER,
    SUBMIT_DIFFERENCES_TOOL,
)
from schmidt.scenarios.spot_the_difference.scene_generation import PlantedDifference
from schmidt.scenarios.spot_the_difference.team_routing import (
    AGENT_ID_TO_TEAM_ID,
    team_id_for_agent,
)
from schmidt.scenarios.spot_the_difference.world import SpotTheDifferenceWorld


def build_mcp_tools(
    world: SpotTheDifferenceWorld,
    judge_provider: LLMProvider,
    get_runtime: Callable[[], ScenarioRuntimeHandle | None],
) -> list[ScenarioMcpTool]:
    """Return the single ``submit_differences`` tool list."""

    async def submit_differences(ctx: ToolContext, differences: list[str]) -> str:
        """Submit the team's final list of differences between the two scenes."""
        agent_id = resolve_agent_id(ctx=ctx)
        if agent_id not in AGENT_ID_TO_TEAM_ID:
            raise ValueError(f"Unknown agent for submit_differences: {agent_id}")
        if world.in_postmortem:
            return "Cannot submit during the post-round discussion phase. Wait for the next round."
        cleaned = [item.strip() for item in differences if item.strip()]
        if len(cleaned) == 0:
            return "Submit at least one difference description."
        case = world.current_case
        if case is None:
            return "There is no active scene to compare yet."
        team_id = team_id_for_agent(agent_id=agent_id)
        if world.is_team_locked(team_id=team_id):
            return (
                f"{ALREADY_SUBMITTED_MARKER}. Your team's answer is already locked for this round."
            )
        if world.has_agent_submitted(team_id=team_id, agent_id=agent_id):
            return (
                f"{ALREADY_SUBMITTED_MARKER}. You have already submitted; waiting for your "
                "partner to submit before the round is scored."
            )
        completed = world.record_agent_submission(team_id=team_id, agent_id=agent_id, items=cleaned)
        if not completed:
            return (
                f"{SUBMISSION_WAITING_MARKER}. Your answer is recorded. The round is not scored "
                "until your partner also submits, so tell them you are done."
            )
        await _judge_and_record_team(
            world=world,
            judge_provider=judge_provider,
            get_runtime=get_runtime,
            team_id=team_id,
            ground_truth=list(case.differences),
        )
        await world.announce_submission_locked(team_id=team_id)
        return (
            f"{SUBMISSION_RECORDED_MARKER}. Your team's answer is locked for this round. "
            "Results are revealed when the round ends."
        )

    return [
        ScenarioMcpTool(
            name=SUBMIT_DIFFERENCES_TOOL,
            description=_tool_description(all_must_submit=world.all_must_submit),
            executor=submit_differences,
        ),
    ]


def _tool_description(all_must_submit: bool) -> str:
    """Build the tool description, noting the both-must-submit rule when enabled."""
    base = (
        "Submit your team's final list of the differences between the two scenes. "
        "Args: differences (a list of short strings, one per difference, each naming the "
        "object involved and how it differs). You must find every difference with no "
        "incorrect guesses to win."
    )
    if all_must_submit:
        return (
            f"{base} BOTH teammates must call this with their own answer: the round is lost for "
            "your team if either of you never submits, and your team is correct only if both "
            "answers name the same full set of differences. Agree with your partner first."
        )
    return (
        f"{base} The first submission from either teammate locks your team's answer for the "
        "round and cannot be changed, so agree with your partner first."
    )


async def _judge_and_record_team(
    world: SpotTheDifferenceWorld,
    judge_provider: LLMProvider,
    get_runtime: Callable[[], ScenarioRuntimeHandle | None],
    team_id: str,
    ground_truth: list[PlantedDifference],
) -> None:
    """Judge every member's answer, record the combined verdict, and log one event each."""
    ground_truth_count = len(ground_truth)
    submissions = world.team_submissions(team_id=team_id)
    characters = world.characters_at_submission(team_id=team_id)
    matched_sets: list[set[int]] = []
    false_positive_counts: list[int] = []
    judged_rows: list[tuple[str, list[str], list[int], int, str]] = []
    for submit_agent_id, items in submissions.items():
        judgment = await judge_submission(
            provider=judge_provider,
            ground_truth=ground_truth,
            submitted_items=items,
        )
        matched = sorted(
            {
                index
                for index in judgment.matched_difference_indices
                if 1 <= index <= ground_truth_count
            }
        )
        matched_sets.append(set(matched))
        false_positive_counts.append(judgment.false_positive_count)
        judged_rows.append(
            (submit_agent_id, items, matched, judgment.false_positive_count, judgment.explanation)
        )
    verdict = combine_team_verdict(
        matched_sets=matched_sets,
        false_positive_counts=false_positive_counts,
        total_differences=ground_truth_count,
    )
    world.record_team_verdict(
        team_id=team_id,
        found_all=verdict.found_all,
        false_positive_count=verdict.false_positive_count,
        found_count=verdict.found_count,
        agreed=verdict.agreed,
    )
    runtime = get_runtime()
    if runtime is None:
        return
    for submit_agent_id, items, matched, false_positives, explanation in judged_rows:
        await runtime.event_logger.log(
            event=DifferenceSubmissionJudged(
                agent_id=submit_agent_id,
                round_number=runtime.current_round,
                team_id=team_id,
                submitted_items=items,
                matched_difference_indices=matched,
                false_positive_count=false_positives,
                found_all=(len(matched) == ground_truth_count and false_positives == 0),
                characters_at_submission=characters,
                judge_explanation=explanation,
            )
        )
