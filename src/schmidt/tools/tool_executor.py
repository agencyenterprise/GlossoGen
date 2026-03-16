"""Executes tool calls by dispatching them through a ToolRegistry."""

import logging

from schmidt.models.tool_definition import ToolCallRequest, ToolCallResult
from schmidt.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Dispatches tool call requests to registered executor functions and captures their results."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def execute(
        self,
        request: ToolCallRequest,
        agent_id: str,
    ) -> ToolCallResult:
        """Look up the tool by name in the registry, invoke it with the request arguments,
        and return a ToolCallResult. If the executor raises an exception, the error message
        is captured in the result with is_error set to True."""
        try:
            executor = self._registry.get_executor(name=request.tool_name)
            output = await executor(agent_id=agent_id, **request.arguments)
            logger.debug(
                "Tool '%s' executed by agent %s (call_id=%s)",
                request.tool_name,
                agent_id,
                request.call_id,
            )
            return ToolCallResult(
                call_id=request.call_id,
                tool_name=request.tool_name,
                output=str(output),
                is_error=False,
            )
        except Exception as e:
            logger.exception("Tool execution failed for '%s'", request.tool_name)
            return ToolCallResult(
                call_id=request.call_id,
                tool_name=request.tool_name,
                output=str(e),
                is_error=True,
            )
