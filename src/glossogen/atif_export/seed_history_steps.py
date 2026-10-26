"""Convert the pydantic-ai history a seat was seeded with into ATIF steps.

A replaced, imported or swapped-in seat starts from history rebuilt from another
agent's turns. That history exists only as pydantic-ai messages, so it carries no
timestamps or token usage, and every step it yields is copied context. The system
prompt it opens with is skipped: the trajectory already starts with one.
"""

from collections.abc import Sequence

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserContent,
    UserPromptPart,
)

from glossogen.atif_export.atif_models import (
    AtifObservation,
    AtifObservationResult,
    AtifStep,
    AtifStepSource,
    AtifToolCall,
)


def build_seed_steps(first_step_id: int, history: list[ModelMessage]) -> list[AtifStep]:
    """One user step per prompt and one agent step per response, numbered from ``first_step_id``."""
    returns_by_call_id = _tool_returns_by_call_id(history=history)
    steps: list[AtifStep] = []
    for message in history:
        if isinstance(message, ModelResponse):
            steps.append(
                _response_step(
                    step_id=first_step_id + len(steps),
                    response=message,
                    returns_by_call_id=returns_by_call_id,
                )
            )
        else:
            for part in message.parts:
                if isinstance(part, UserPromptPart):
                    steps.append(
                        _seed_step(
                            step_id=first_step_id + len(steps),
                            source=AtifStepSource.USER,
                            message=_prompt_text(content=part.content),
                        )
                    )
    return steps


def _tool_returns_by_call_id(history: list[ModelMessage]) -> dict[str, str]:
    returns: dict[str, str] = {}
    for message in history:
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if isinstance(part, ToolReturnPart):
                returns[part.tool_call_id] = part.model_response_str()
    return returns


def _response_step(
    step_id: int,
    response: ModelResponse,
    returns_by_call_id: dict[str, str],
) -> AtifStep:
    text = "\n".join(part.content for part in response.parts if isinstance(part, TextPart))
    thinking = "\n".join(part.content for part in response.parts if isinstance(part, ThinkingPart))
    calls = [part for part in response.parts if isinstance(part, ToolCallPart)]
    step = _seed_step(step_id=step_id, source=AtifStepSource.AGENT, message=text)
    if thinking:
        step.reasoning_content = thinking
    if calls:
        step.tool_calls = [
            AtifToolCall(
                tool_call_id=call.tool_call_id,
                function_name=call.tool_name,
                arguments=call.args_as_dict(),
            )
            for call in calls
        ]
        results = [
            AtifObservationResult(
                source_call_id=call.tool_call_id,
                content=returns_by_call_id[call.tool_call_id],
            )
            for call in calls
            if call.tool_call_id in returns_by_call_id
        ]
        if results:
            step.observation = AtifObservation(results=results)
    return step


def _seed_step(step_id: int, source: AtifStepSource, message: str) -> AtifStep:
    return AtifStep(
        step_id=step_id,
        timestamp=None,
        source=source,
        message=message,
        model_name=None,
        reasoning_content=None,
        tool_calls=None,
        observation=None,
        metrics=None,
        is_copied_context=True,
        llm_call_count=None,
        extra={"kind": "seed_history"},
    )


def _prompt_text(content: str | Sequence[UserContent]) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(item for item in content if isinstance(item, str))
