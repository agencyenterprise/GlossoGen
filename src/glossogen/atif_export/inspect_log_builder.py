"""Agent trajectories as an Inspect-format log, which Docent imports with Upload Inspect Log.

Each ATIF trajectory becomes one sample, and each sample holds one agent's messages
in Inspect's chat message shape. The log holds the fields that Docent's Inspect
importer reads: ``samples``, and each sample's ``id``, ``epoch``, ``messages`` and
``metadata``. Inspect's own tools need more fields than these and do not open it.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from glossogen.atif_export.atif_models import AtifStep, AtifStepSource, AtifTrajectory

INSPECT_LOG_FILE_NAME = "inspect_log.json"


class InspectContentText(BaseModel):
    """Text that a model wrote."""

    type: Literal["text"] = "text"
    text: str


class InspectContentReasoning(BaseModel):
    """Reasoning that a model returned."""

    type: Literal["reasoning"] = "reasoning"
    reasoning: str


class InspectToolCall(BaseModel):
    """One tool call in an assistant message."""

    id: str
    type: Literal["function"] = "function"
    function: str
    arguments: dict[str, Any]


class InspectSystemMessage(BaseModel):
    """A system prompt, or a context compaction summary."""

    role: Literal["system"] = "system"
    content: str
    metadata: dict[str, Any]


class InspectUserMessage(BaseModel):
    """A prompt that the runner gave the agent."""

    role: Literal["user"] = "user"
    content: str
    metadata: dict[str, Any]


class InspectAssistantMessage(BaseModel):
    """One model response: its reasoning, text and tool calls."""

    role: Literal["assistant"] = "assistant"
    content: list[InspectContentReasoning | InspectContentText]
    tool_calls: list[InspectToolCall] | None
    model: str | None
    metadata: dict[str, Any]


class InspectToolMessage(BaseModel):
    """The result of one tool call."""

    role: Literal["tool"] = "tool"
    content: str
    tool_call_id: str
    function: str
    metadata: dict[str, Any]


InspectMessage = Annotated[
    InspectSystemMessage | InspectUserMessage | InspectAssistantMessage | InspectToolMessage,
    Field(discriminator="role"),
]


class InspectSample(BaseModel):
    """One agent's trajectory through one run, as one sample."""

    id: str
    epoch: int
    messages: list[InspectMessage]
    metadata: dict[str, Any]


class InspectLog(BaseModel):
    """An Inspect-format log holding one sample per trajectory."""

    samples: list[InspectSample]


def build_inspect_samples(trajectories: list[AtifTrajectory]) -> list[InspectSample]:
    """One sample per trajectory, in the order given."""
    return [_build_sample(trajectory=trajectory) for trajectory in trajectories]


def serialize_inspect_log(log: InspectLog) -> str:
    """The log as JSON, with unset optional fields omitted."""
    return log.model_dump_json(exclude_none=True)


def _build_sample(trajectory: AtifTrajectory) -> InspectSample:
    """A trajectory's steps as messages, with the run, agent and model as metadata."""
    messages: list[InspectMessage] = []
    for step in trajectory.steps:
        messages.extend(_step_messages(step=step))
    return InspectSample(
        id=trajectory.trajectory_id,
        epoch=1,
        messages=messages,
        metadata={
            "glossogen_run": trajectory.session_id,
            "scenario": trajectory.extra["scenario_name"],
            "agent_id": trajectory.agent.extra["agent_id"],
            "model": trajectory.agent.model_name,
            "provider": trajectory.agent.extra["provider"],
            "generation": trajectory.extra["generation"],
            "scenario_config": trajectory.extra["scenario_config"],
        },
    )


def _step_messages(step: AtifStep) -> list[InspectMessage]:
    """A system or user step as one message; an agent step as its response and its results."""
    metadata = _step_metadata(step=step)
    if step.source == AtifStepSource.SYSTEM:
        return [InspectSystemMessage(content=step.message, metadata=metadata)]
    if step.source == AtifStepSource.USER:
        return [InspectUserMessage(content=step.message, metadata=metadata)]
    return [_assistant_message(step=step, metadata=metadata), *_tool_messages(step=step)]


def _step_metadata(step: AtifStep) -> dict[str, Any]:
    """The step's id, whether it is copied context, and the step's own ``extra``."""
    return {
        "step_id": step.step_id,
        "is_copied_context": step.is_copied_context is True,
        **step.extra,
    }


def _assistant_message(step: AtifStep, metadata: dict[str, Any]) -> InspectAssistantMessage:
    """An agent step's reasoning, text and tool calls."""
    content: list[InspectContentReasoning | InspectContentText] = []
    if step.reasoning_content:
        content.append(InspectContentReasoning(reasoning=step.reasoning_content))
    if step.message:
        content.append(InspectContentText(text=step.message))
    tool_calls = None
    if step.tool_calls:
        tool_calls = [
            InspectToolCall(
                id=call.tool_call_id, function=call.function_name, arguments=call.arguments
            )
            for call in step.tool_calls
        ]
    return InspectAssistantMessage(
        content=content,
        tool_calls=tool_calls,
        model=step.model_name,
        metadata=metadata,
    )


def _tool_messages(step: AtifStep) -> list[InspectToolMessage]:
    """One message per tool result of an agent step, named after the call it answers."""
    if step.observation is None or step.tool_calls is None:
        return []
    function_by_call_id = {call.tool_call_id: call.function_name for call in step.tool_calls}
    return [
        InspectToolMessage(
            content=result.content,
            tool_call_id=result.source_call_id,
            function=function_by_call_id[result.source_call_id],
            metadata={"step_id": step.step_id},
        )
        for result in step.observation.results
    ]
