"""LLM-backed judges for the container_yard_stacking scenario.

Two judges share this module. ``judge_truck_destination`` parses the yard
operator's freetext truck-destination argument and reports whether it
correctly identifies the round's correct crane station, the correct
transfer pad, and the incoming container by ID. ``judge_crane_move`` parses
the crane operator's freetext action into a structured (container_id,
source, destination) tuple, then reports whether that parsed move matches
the next expected step in the ground-truth plan and whether the physical
preconditions (source currently holds the container, destination currently
empty) hold given the current world stack snapshot rendered into the user
message.
"""

import logging
from pathlib import Path

from pydantic import BaseModel

from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.scenarios.container_yard_stacking.events import (
    ContainerYardCraneMoveJudgment,
    ContainerYardCraneMoveStep,
    ContainerYardTruckJudgment,
)
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
_renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])


class TruckJudgmentResult(BaseModel):
    """Structured output from the truck destination judge."""

    judgment: ContainerYardTruckJudgment
    explanation: str


class CraneMoveJudgmentResult(BaseModel):
    """Structured output from the crane move judge."""

    parsed_move: ContainerYardCraneMoveStep
    judgment: ContainerYardCraneMoveJudgment
    explanation: str


async def judge_truck_destination(
    provider: LLMProvider,
    expected_station: str,
    expected_pad: str,
    expected_container_id: str,
    submitted_destination_text: str,
) -> TruckJudgmentResult:
    """Ask the LLM judge whether the truck destination matches the round's ground truth."""
    system_prompt = _renderer.render(
        template_name="truck_judge.jinja",
        template_variables={},
    )
    user_message = (
        f"Correct crane station: {expected_station}\n"
        f"Correct transfer pad: {expected_pad}\n"
        f"Incoming container id: {expected_container_id}\n\n"
        f"Yard operator's truck destination text:\n{submitted_destination_text}"
    )
    logger.info(
        "Truck judge input: station=%s pad=%s container=%s text=[%s]",
        expected_station,
        expected_pad,
        expected_container_id,
        submitted_destination_text,
    )
    result = await provider.generate_structured(
        system_prompt=system_prompt,
        messages=[LLMMessage(role="user", content=user_message)],
        output_schema=TruckJudgmentResult,
    )
    logger.info(
        "Truck judge result: judgment=%s explanation=%s",
        result.judgment.model_dump(),
        result.explanation,
    )
    return result


async def judge_crane_move(
    provider: LLMProvider,
    expected_next_move: ContainerYardCraneMoveStep,
    move_index: int,
    world_snapshot: str,
    submitted_action_text: str,
) -> CraneMoveJudgmentResult:
    """Ask the LLM judge to parse a freetext crane move and rule on its validity."""
    system_prompt = _renderer.render(
        template_name="crane_move_judge.jinja",
        template_variables={},
    )
    user_message = (
        f"Expected next move (index {move_index}):\n"
        f"- container_id: {expected_next_move.container_id}\n"
        f"- source: {expected_next_move.source}\n"
        f"- destination: {expected_next_move.destination}\n\n"
        f"Current world state:\n{world_snapshot}\n\n"
        f"Crane operator's action text:\n{submitted_action_text}"
    )
    logger.info(
        "Crane move judge input: move_index=%d expected=%s text=[%s]",
        move_index,
        expected_next_move.model_dump(),
        submitted_action_text,
    )
    result = await provider.generate_structured(
        system_prompt=system_prompt,
        messages=[LLMMessage(role="user", content=user_message)],
        output_schema=CraneMoveJudgmentResult,
    )
    logger.info(
        "Crane move judge result: parsed=%s judgment=%s explanation=%s",
        result.parsed_move.model_dump(),
        result.judgment.model_dump(),
        result.explanation,
    )
    return result
