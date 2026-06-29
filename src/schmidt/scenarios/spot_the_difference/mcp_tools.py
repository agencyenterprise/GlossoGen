"""The single MCP tool the spot_the_difference scenario exposes to its agents.

``submit_differences`` is either viewer's one action: submit the team's
free-text list of the differences between the two scenes. The first call locks
the team's answer for the round (snapshotting its character count); an LLM
judge then scores the list against the round's planted differences and the
verdict is logged as a JSONL event. The result is not revealed at submit time
— it is announced when the round ends — so the submission stays one-shot.
"""

from typing import Callable

from schmidt.llm.provider import LLMProvider
from schmidt.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from schmidt.scenario_protocol import ScenarioRuntimeHandle
from schmidt.scenarios.spot_the_difference.difference_judge import judge_submission
from schmidt.scenarios.spot_the_difference.events import DifferenceSubmissionJudged
from schmidt.scenarios.spot_the_difference.ids import (
    ALREADY_SUBMITTED_MARKER,
    SUBMISSION_RECORDED_MARKER,
    SUBMIT_DIFFERENCES_TOOL,
)
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
        locked_characters = world.try_lock_submission(team_id=team_id)
        if locked_characters is None:
            return (
                f"{ALREADY_SUBMITTED_MARKER}. Your team already submitted this round; "
                "the answer is locked."
            )
        judgment = await judge_submission(
            provider=judge_provider,
            ground_truth=list(case.differences),
            submitted_items=cleaned,
        )
        matched = sorted(
            {
                index
                for index in judgment.matched_difference_indices
                if 1 <= index <= len(case.differences)
            }
        )
        found_count = len(matched)
        found_all = found_count == len(case.differences) and judgment.false_positive_count == 0
        world.record_submission_result(
            team_id=team_id,
            found_all=found_all,
            false_positive_count=judgment.false_positive_count,
            found_count=found_count,
        )
        runtime = get_runtime()
        if runtime is not None:
            await runtime.event_logger.log(
                event=DifferenceSubmissionJudged(
                    agent_id=agent_id,
                    round_number=runtime.current_round,
                    team_id=team_id,
                    submitted_items=cleaned,
                    matched_difference_indices=matched,
                    false_positive_count=judgment.false_positive_count,
                    found_all=found_all,
                    characters_at_submission=locked_characters,
                    judge_explanation=judgment.explanation,
                )
            )
        await world.announce_submission_locked(team_id=team_id)
        return (
            f"{SUBMISSION_RECORDED_MARKER}. Your team's answer ({len(cleaned)} difference(s)) is "
            "locked for this round. Results are revealed when the round ends."
        )

    return [
        ScenarioMcpTool(
            name=SUBMIT_DIFFERENCES_TOOL,
            description=(
                "Submit your team's final list of the differences between the two scenes. "
                "Args: differences (a list of short strings, one per difference, each naming the "
                "object involved and how it differs). The first submission locks your team's "
                "answer for the round and cannot be changed, so agree with your partner first. "
                "You must find every difference with no incorrect guesses to win."
            ),
            executor=submit_differences,
        ),
    ]
