"""The contract a scenario implements to surface its own data on the run-detail API.

A scenario returns one :class:`ScenarioRunDetailExtension` from
:meth:`glossogen.scenario_protocol.SimulationScenario.run_detail_extension`. The
server builds the ``scenario_extras`` discriminated union on ``RunDetailResponse``
from each extension's ``extras_model_cls``, and calls ``build_extras`` after the
generic event walk. :func:`pair_with_tool_calls` is the walk the scenarios that
log a verdict per tool call share to key that verdict by the call's ``call_id``.

Kept out of :mod:`glossogen.server` because the scenario contract imports it.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import ClassVar, Protocol

from pydantic import BaseModel

from glossogen.models.event import SimulationEvent, ToolResultReceived
from glossogen.run_detail_types import AgentDetail, ChannelMessage


class ScenarioRunExtrasBase(BaseModel):
    """Abstract base for the polymorphic payload attached to ``RunDetailResponse.scenario_extras``.

    Each subclass declares ``scenario_name: Literal["<name>"]`` as the
    discriminator field. Pydantic dispatches between subclasses on that field
    when validating the discriminated union.
    """


class ScenarioRunDetailExtension(ABC):
    """Per-scenario hook that materializes ``ScenarioRunExtrasBase`` from a run's event log.

    Each subclass declares the Pydantic class that holds its extras payload
    (``extras_model_cls``) and any custom SSE event classes the scenario emits
    over the live stream (``sse_event_classes``). Both are read at server
    startup to build the discriminated unions on ``RunDetailResponse`` and the
    SSE event union.
    """

    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]]
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]]

    @abstractmethod
    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, AgentDetail],
        messages: list[ChannelMessage],
    ) -> ScenarioRunExtrasBase:
        """Walk ``events`` and return the scenario-specific extras payload.

        ``agents_by_id`` and ``messages`` are the already-materialized
        platform views for the same run; extensions reuse them instead
        of re-indexing the event list.
        """


class AgentScopedEvent(Protocol):
    """An event that names the agent it was logged for."""

    agent_id: str


def pair_with_tool_calls[Judged: AgentScopedEvent, Payload](
    events: list[SimulationEvent],
    judged_event_cls: type[Judged],
    tool_names: frozenset[str],
    build_payload: Callable[[Judged], Payload],
) -> dict[str, Payload]:
    """Key a payload built from each ``judged_event_cls`` event by its tool call's ``call_id``.

    MCP does not hand a tool its ``call_id``, so the verdict event cannot carry it.
    Walking ``events`` in order, each verdict is queued for its agent, and each
    ``tool_names`` result that agent receives takes the oldest queued one. A result
    with nothing queued is left unpaired.
    """
    pending_by_agent: dict[str, list[Payload]] = {}
    payload_by_call_id: dict[str, Payload] = {}
    for event in events:
        if isinstance(event, judged_event_cls):
            pending_by_agent.setdefault(event.agent_id, []).append(build_payload(event))
        elif isinstance(event, ToolResultReceived) and event.tool_name in tool_names:
            queue = pending_by_agent.get(event.agent_id)
            if queue:
                payload_by_call_id[event.call_id] = queue.pop(0)
    return payload_by_call_id
