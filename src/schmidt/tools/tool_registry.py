"""Registry that maps tool names to their specifications and async executor functions."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from schmidt.models.tool_definition import ToolSpec

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Stores tool specifications and their corresponding executor callables, keyed by tool name."""

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._executors: dict[str, Callable[..., Awaitable[str]]] = {}

    def register(
        self,
        spec: ToolSpec,
        executor: Callable[..., Awaitable[str]],
    ) -> None:
        """Add a tool spec and its executor to the registry, keyed by the spec's name."""
        self._specs[spec.name] = spec
        self._executors[spec.name] = executor
        logger.debug("Registered tool: %s", spec.name)

    def get_specs(self, names: list[str]) -> list[ToolSpec]:
        """Return a list of ToolSpecs matching the given names, in the same order.

        Raises KeyError with a diagnostic message if any name is not registered.
        """
        missing = [n for n in names if n not in self._specs]
        if missing:
            available = sorted(self._specs.keys())
            raise KeyError(f"Tool(s) not registered: {missing}. Available: {available}")
        return [self._specs[name] for name in names]

    def get_executor(self, name: str) -> Callable[..., Awaitable[Any]]:
        """Return the async executor callable for the given tool
        name. Raises KeyError if not found.
        """
        return self._executors[name]
