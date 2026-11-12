"""The contract a scenario implements to surface its own data on the run-detail API.

A scenario returns one :class:`ScenarioRunDetailExtension` from
:meth:`glossogen.scenario_contract.protocol.SimulationScenario.run_detail_extension`. The
server calls ``build_extras`` after the generic event walk and returns the
result as ``RunDetailResponse.scenario_extras``, and publishes each extension's
``extras_model_cls`` and ``sse_event_classes`` in its API schema.
:func:`pair_with_tool_calls` is the walk the scenarios that log a verdict per
tool call share to key that verdict by the call's ``call_id``, and
:func:`mirror_events` the walk that copies each event of one class into the
response model that mirrors it.

Kept out of :mod:`glossogen.server` because the scenario contract imports it.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import ClassVar, Protocol

from pydantic import BaseModel

from glossogen.models.event import SimulationEvent, ToolResultReceived
from glossogen.scenario_contract.run_detail_types import AgentDetail, ChannelMessage


class ScenarioRunExtrasBase(BaseModel):
    """Abstract base for the polymorphic payload attached to ``RunDetailResponse.scenario_extras``.

    Each subclass declares ``scenario_name: Literal["<name>"]`` as the
    discriminator field. The server does not validate extras against a union:
    ``RunDetailResponse.scenario_extras`` is typed as this base and serializes as
    the subclass ``build_extras`` returned. The API schema publishes the
    discriminated union of every loaded scenario's subclass on ``scenario_name``,
    which is what the frontend's types are generated from.
    """


class ScenarioRunDetailExtension(ABC):
    """Per-scenario hook that materializes ``ScenarioRunExtrasBase`` from a run's event log.

    Each subclass declares the Pydantic class that holds its extras payload
    (``extras_model_cls``) and any custom SSE event classes the scenario emits
    over the live stream (``sse_event_classes``). The app factory reads both
    when it builds the app, to publish the ``scenario_extras`` and SSE event
    unions in the API schema.
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


def mirror_events[Mirror: BaseModel](
    events: list[SimulationEvent],
    event_cls: type[BaseModel],
    mirror_cls: type[Mirror],
) -> list[Mirror]:
    """Copy each ``event_cls`` event in ``events``, in log order, into a ``mirror_cls``.

    Fields are matched by name, nested models included. Event fields that
    ``mirror_cls`` does not declare are dropped. A required field it declares that
    the event lacks raises a ``ValidationError``; a defaulted one keeps its default.
    """
    return [
        mirror_cls.model_validate(event, from_attributes=True)
        for event in events
        if isinstance(event, event_cls)
    ]


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
