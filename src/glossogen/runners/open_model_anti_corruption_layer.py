"""Drops the arguments an open-weight model sends that the called tool does not declare.

``OpenModelAntiCorruptionLayer`` runs before pydantic-ai validates a tool call
from an agent on an open-weight provider, so the tools keep their strict schemas
and agents on any other provider reach them unchanged. It drops the top-level
arguments the tool's schema neither declares nor accepts as extra, such as the
``wait_for`` in ``list_channels(wait_for="any")``, a tool that takes no arguments.

Each drop is logged with the call's id. The event log keeps the call as the model
sent it, since ``ToolCallInvoked`` is logged from the model's own tool-call part.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, cast

from pydantic_ai.capabilities import AbstractCapability, AgentCapability, RawToolArgs
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import RunContext, ToolDefinition

from glossogen.model_catalog import OPEN_WEIGHT_PROVIDERS, Provider

logger = logging.getLogger(__name__)


@dataclass
class OpenModelAntiCorruptionLayer(AbstractCapability[None]):
    """Drops the arguments a tool does not take from an agent's tool calls.

    A call whose arguments are not a JSON object, or whose tool accepts extra
    arguments, passes through as sent, and validation reports it as usual.
    """

    agent_id: str

    async def before_tool_validate(
        self,
        ctx: RunContext[None],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: RawToolArgs,
    ) -> RawToolArgs:
        """Return ``args`` without the keys ``tool_def`` does not declare."""
        _ = ctx
        arguments = arguments_object(args=args, agent_id=self.agent_id, call=call)
        if arguments is None:
            return args
        dropped = undeclared_arguments(arguments=arguments, tool_def=tool_def)
        if not dropped:
            return args
        logger.warning(
            "Agent %s called %s (call %s) with arguments it does not take, dropped: %s",
            self.agent_id,
            tool_def.name,
            call.tool_call_id,
            ", ".join(dropped),
        )
        return {key: value for key, value in arguments.items() if key not in dropped}


def arguments_object(args: RawToolArgs, agent_id: str, call: ToolCallPart) -> dict[str, Any] | None:
    """Return ``args`` as a dict, or None when it is not a JSON object. Invalid JSON is logged."""
    if isinstance(args, dict):
        return args
    try:
        parsed = json.loads(args)
    except json.JSONDecodeError:
        logger.exception(
            "Agent %s sent %s (call %s) arguments that are not JSON; validation reports them",
            agent_id,
            call.tool_name,
            call.tool_call_id,
        )
        return None
    if isinstance(parsed, dict):
        return cast(dict[str, Any], parsed)
    return None


def undeclared_arguments(arguments: dict[str, Any], tool_def: ToolDefinition) -> list[str]:
    """Return the keys of ``arguments`` a tool neither declares nor accepts as extra, sorted."""
    schema = tool_def.parameters_json_schema
    if schema.get("additionalProperties", True) is not False:
        return []
    declared = schema.get("properties", {})
    return sorted(key for key in arguments if key not in declared)


def open_model_capabilities(provider: Provider, agent_id: str) -> list[AgentCapability[None]]:
    """Return the anti-corruption layer for an agent on an open-weight provider, else nothing."""
    if provider in OPEN_WEIGHT_PROVIDERS:
        return [OpenModelAntiCorruptionLayer(agent_id=agent_id)]
    return []
