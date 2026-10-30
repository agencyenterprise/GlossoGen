"""The run-level LLM judge shared by the language-emergence metrics.

``neologism``, ``language_strangeness``, ``slang_emergence`` and
``shorthand_codes`` each show the judge every round's primary-channel transcript
in one call, get back notes on the rounds where their phenomenon appeared, and
score the number of distinct rounds noted. They differ in the user template, the
output schema, and which of the schema's fields qualify the summary.
"""

import logging
from collections.abc import Callable, Mapping
from typing import NamedTuple, TypeVar

from pydantic import BaseModel

from glossogen.evaluation.metric_core.measurement import Measurement, RoundNote, merge_round_notes
from glossogen.evaluation.metric_core.pristine_text_index import build_pristine_text_index
from glossogen.evaluation.prompts.prompt_renderer import render_evaluator_prompt
from glossogen.evaluation.round_transcript_builder import build_round_transcripts
from glossogen.llm.provider import LLMMessage, LLMProvider
from glossogen.models.event import SimulationEvent
from glossogen.scenario_base import ScenarioBase

logger = logging.getLogger(__name__)

JudgeOutputT = TypeVar("JudgeOutputT", bound=BaseModel)


class FlaggedRoundVerdict(NamedTuple):
    """The parts of a judge's answer the measurement is built from.

    ``qualifiers`` are short phrases appended to the summary in parentheses,
    such as ``"mutually adopted"``; an empty list appends nothing.
    """

    per_round_notes: list[RoundNote]
    qualifiers: list[str]
    explanation: str


async def judge_flagged_rounds(
    *,
    metric_name: str,
    finding: str,
    events: list[SimulationEvent],
    scenario: ScenarioBase,
    llm_provider: LLMProvider,
    user_template_name: str,
    extra_template_variables: Mapping[str, object],
    output_schema: type[JudgeOutputT],
    read_verdict: Callable[[JudgeOutputT], FlaggedRoundVerdict],
) -> list[Measurement]:
    """Ask the judge once about the whole run and count the rounds it flagged.

    The user template receives the round transcripts as ``rounds`` plus
    ``extra_template_variables``. ``finding`` names what a flagged round
    contained, as it reads in the summary and the score unit. Returns ``[]``
    when the run has no messages on any channel to judge.
    """
    round_transcripts = build_round_transcripts(
        events=events,
        scenario=scenario,
        pristine_index=build_pristine_text_index(events=events),
    )
    if not round_transcripts:
        logger.info("%s: skipping — no messages found", metric_name)
        return []

    judge_prompt = render_evaluator_prompt(
        template_name=user_template_name,
        template_variables={"rounds": round_transcripts, **extra_template_variables},
    )
    result = await llm_provider.generate_structured(
        system_prompt=render_evaluator_prompt(
            template_name="evaluator_system.jinja",
            template_variables={},
        ),
        messages=[LLMMessage(role="user", content=judge_prompt)],
        output_schema=output_schema,
    )
    verdict = read_verdict(result)

    per_round = merge_round_notes(notes=verdict.per_round_notes)
    qualifier_text = ""
    if verdict.qualifiers:
        qualifier_text = f" ({'; '.join(verdict.qualifiers)})"
    summary = (
        f"{len(per_round)}/{len(round_transcripts)} rounds contained "
        f"{finding}{qualifier_text}. {verdict.explanation}"
    )
    return [
        Measurement(
            metric_name=metric_name,
            score=float(len(per_round)),
            score_unit=f"rounds with {finding} (out of {len(round_transcripts)})",
            summary=summary,
            per_round=per_round,
            per_agent=[],
        )
    ]
