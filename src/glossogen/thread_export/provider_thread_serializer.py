"""Serialize a pydantic-ai ``list[ModelMessage]`` into a provider-native request body.

Walks the reconstructed history and emits an ``AnthropicRequest`` or
``OpenAIRequest`` whose ``messages`` (and Anthropic ``system``) match the
provider wire format exactly, so the result is a drop-in API body. ``SystemPromptPart``
is folded into Anthropic's top-level ``system`` / a leading OpenAI ``system`` message;
tool calls and returns map to native ``tool_use`` / ``tool_result`` (Anthropic) or
``tool_calls`` / ``tool`` messages (OpenAI). ``ThinkingPart`` is dropped unless
``include_thinking`` (then rendered as text, since replaying provider reasoning blocks
raw requires signatures). ``flatten_tools`` renders every tool call/return as plain
text instead of structured tool blocks, yielding a body that needs no tool config.
"""

import json
from collections.abc import Sequence
from typing import Literal

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from glossogen.thread_export.thread_export_models import (
    AnthropicBlock,
    AnthropicMessage,
    AnthropicRequest,
    AnthropicTextBlock,
    AnthropicToolResultBlock,
    AnthropicToolUseBlock,
    OpenAIAssistantMessage,
    OpenAIFunctionCall,
    OpenAIMessage,
    OpenAIRequest,
    OpenAISystemMessage,
    OpenAIToolCall,
    OpenAIToolMessage,
    OpenAIUserMessage,
)


def _coerce_to_text(content: object) -> str:
    """Render arbitrary part content (str, list, or structured payload) as text."""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, default=str)


def _flattened_tool_call_text(part: ToolCallPart) -> str:
    """Plain-text rendering of a tool call for ``flatten_tools`` mode."""
    return f"[tool_call {part.tool_name}({part.args_as_json_str()})]"


def _flattened_tool_result_text(part: ToolReturnPart) -> str:
    """Plain-text rendering of a tool return for ``flatten_tools`` mode."""
    return f"[tool_result {part.tool_name}]\n{_coerce_to_text(content=part.content)}"


def _append_anthropic_turn(
    turns: list[AnthropicMessage],
    role: Literal["user", "assistant"],
    blocks: list[AnthropicBlock],
) -> None:
    """Append blocks to ``turns``, merging into the last turn when the role repeats.

    Anthropic requires alternating user/assistant turns; consecutive same-role
    requests/responses (e.g. a tool-result turn followed by the continue-prompt
    turn) are coalesced into one message so the body is valid.
    """
    if not blocks:
        return
    if turns and turns[-1].role == role:
        turns[-1].content.extend(blocks)
        return
    turns.append(AnthropicMessage(role=role, content=blocks))


def to_anthropic_request(
    messages: list[ModelMessage],
    model: str,
    include_thinking: bool,
    flatten_tools: bool,
) -> AnthropicRequest:
    """Serialize the history into an Anthropic Messages API body."""
    system_parts: list[str] = []
    turns: list[AnthropicMessage] = []

    for message in messages:
        if isinstance(message, ModelRequest):
            user_blocks: list[AnthropicBlock] = []
            for part in message.parts:
                if isinstance(part, SystemPromptPart):
                    system_parts.append(_coerce_to_text(content=part.content))
                elif isinstance(part, UserPromptPart):
                    user_blocks.append(
                        AnthropicTextBlock(text=_coerce_to_text(content=part.content))
                    )
                elif isinstance(part, ToolReturnPart):
                    if flatten_tools:
                        user_blocks.append(
                            AnthropicTextBlock(text=_flattened_tool_result_text(part=part))
                        )
                    else:
                        user_blocks.append(
                            AnthropicToolResultBlock(
                                tool_use_id=part.tool_call_id,
                                content=_coerce_to_text(content=part.content),
                            )
                        )
            _append_anthropic_turn(turns=turns, role="user", blocks=user_blocks)
        else:
            assistant_blocks: list[AnthropicBlock] = []
            for part in message.parts:
                if isinstance(part, TextPart):
                    assistant_blocks.append(AnthropicTextBlock(text=part.content))
                elif isinstance(part, ThinkingPart):
                    if include_thinking:
                        assistant_blocks.append(AnthropicTextBlock(text=part.content))
                elif isinstance(part, ToolCallPart):
                    if flatten_tools:
                        assistant_blocks.append(
                            AnthropicTextBlock(text=_flattened_tool_call_text(part=part))
                        )
                    else:
                        assistant_blocks.append(
                            AnthropicToolUseBlock(
                                id=part.tool_call_id,
                                name=part.tool_name,
                                input=part.args_as_dict(),
                            )
                        )
            _append_anthropic_turn(turns=turns, role="assistant", blocks=assistant_blocks)

    return AnthropicRequest(
        model=model,
        system="\n\n".join(system_parts),
        messages=turns,
    )


def _openai_messages_from_response(
    parts: Sequence[object],
    include_thinking: bool,
    flatten_tools: bool,
) -> list[OpenAIMessage]:
    """Render one ``ModelResponse`` as a single OpenAI assistant message."""
    text_fragments: list[str] = []
    tool_calls: list[OpenAIToolCall] = []
    for part in parts:
        if isinstance(part, TextPart):
            text_fragments.append(part.content)
        elif isinstance(part, ThinkingPart):
            if include_thinking:
                text_fragments.append(part.content)
        elif isinstance(part, ToolCallPart):
            if flatten_tools:
                text_fragments.append(_flattened_tool_call_text(part=part))
            else:
                tool_calls.append(
                    OpenAIToolCall(
                        id=part.tool_call_id,
                        function=OpenAIFunctionCall(
                            name=part.tool_name,
                            arguments=part.args_as_json_str(),
                        ),
                    )
                )
    content = "\n".join(text_fragments)
    if not content and not tool_calls:
        return []
    return [
        OpenAIAssistantMessage(
            content=content if content else None,
            tool_calls=tool_calls if tool_calls else None,
        )
    ]


def _openai_messages_from_request(
    parts: Sequence[object],
    flatten_tools: bool,
) -> tuple[list[str], list[OpenAIMessage]]:
    """Render one ``ModelRequest`` into system-prompt strings and OpenAI messages."""
    system_parts: list[str] = []
    messages: list[OpenAIMessage] = []
    for part in parts:
        if isinstance(part, SystemPromptPart):
            system_parts.append(_coerce_to_text(content=part.content))
        elif isinstance(part, UserPromptPart):
            messages.append(OpenAIUserMessage(content=_coerce_to_text(content=part.content)))
        elif isinstance(part, ToolReturnPart):
            if flatten_tools:
                messages.append(OpenAIUserMessage(content=_flattened_tool_result_text(part=part)))
            else:
                messages.append(
                    OpenAIToolMessage(
                        tool_call_id=part.tool_call_id,
                        content=_coerce_to_text(content=part.content),
                    )
                )
    return system_parts, messages


def to_openai_request(
    messages: list[ModelMessage],
    model: str,
    include_thinking: bool,
    flatten_tools: bool,
) -> OpenAIRequest:
    """Serialize the history into an OpenAI Chat Completions body."""
    system_parts: list[str] = []
    body_messages: list[OpenAIMessage] = []

    for message in messages:
        if isinstance(message, ModelRequest):
            request_system, request_messages = _openai_messages_from_request(
                parts=message.parts,
                flatten_tools=flatten_tools,
            )
            system_parts.extend(request_system)
            body_messages.extend(request_messages)
        else:
            body_messages.extend(
                _openai_messages_from_response(
                    parts=message.parts,
                    include_thinking=include_thinking,
                    flatten_tools=flatten_tools,
                )
            )

    leading: list[OpenAIMessage] = []
    if system_parts:
        leading.append(OpenAISystemMessage(content="\n\n".join(system_parts)))
    return OpenAIRequest(model=model, messages=leading + body_messages)
