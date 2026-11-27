"""The ``send_drawing`` tool a viewer is offered under the canvas medium.

A viewer lists the pixels to paint on the run's canvas. The drawing goes on its
team's link when viewers broadcast, or to one named teammate when they message
one at a time, and the runtime delivers it to the recipients as an image. A
drawing is refused in the discussion phase and on the discussion channels,
which carry text.
"""

from collections.abc import Awaitable, Callable

from pydantic import ValidationError

from glossogen.models.canvas import CanvasDrawing, CanvasPixel
from glossogen.models.channel import DIRECT_CHANNEL_PREFIX
from glossogen.models.mcp_responses import SendMessageResult, SendStatus
from glossogen.scenario_contract.scenario_base import ScenarioRuntimeHandle
from glossogen.scenario_contract.scenario_tool import ScenarioTool
from glossogen.scenarios.spot_the_intersection.link_medium import (
    DRAWING_REFUSED_IN_DISCUSSION,
    DRAWING_REFUSED_ON_CHANNEL,
    SEND_DRAWING_TOOL,
    send_drawing_description,
)


class DrawingSender:
    """Posts viewers' drawings on a ``width`` x ``height`` canvas through the runtime.

    ``link_channel_ids`` are the channels a drawing may go on besides direct
    channels. ``channel_for_recipient`` turns a one-to-one ``to`` into the
    channel it reaches.
    """

    def __init__(
        self,
        width: int,
        height: int,
        link_channel_ids: frozenset[str],
        in_postmortem: Callable[[], bool],
        get_runtime: Callable[[], ScenarioRuntimeHandle],
        channel_for_recipient: Callable[[str, str], Awaitable[str]],
    ) -> None:
        self._width = width
        self._height = height
        self._link_channel_ids = link_channel_ids
        self._in_postmortem = in_postmortem
        self._get_runtime = get_runtime
        self._channel_for_recipient = channel_for_recipient

    def tool(self, one_to_one: bool) -> ScenarioTool:
        """The ``send_drawing`` tool, addressed by teammate when ``one_to_one``."""
        executor: Callable[..., Awaitable[SendMessageResult]] = self.draw_on_channel
        if one_to_one:
            executor = self.draw_to_teammate
        return ScenarioTool(
            name=SEND_DRAWING_TOOL,
            description=send_drawing_description(
                width=self._width, height=self._height, one_to_one=one_to_one
            ),
            executor=executor,
        )

    async def draw_on_channel(
        self, agent_id: str, channel_id: str, pixels: list[CanvasPixel], force: bool
    ) -> SendMessageResult:
        """Post a drawing of ``pixels`` on ``channel_id``."""
        return await self._send(
            agent_id=agent_id, channel_id=channel_id, pixels=pixels, force=force
        )

    async def draw_to_teammate(
        self, agent_id: str, to: str, pixels: list[CanvasPixel], force: bool
    ) -> SendMessageResult:
        """Post a drawing of ``pixels`` to the teammate ``to`` on their direct channel."""
        channel_id = await self._channel_for_recipient(agent_id, to)
        return await self._send(
            agent_id=agent_id, channel_id=channel_id, pixels=pixels, force=force
        )

    async def _send(
        self, agent_id: str, channel_id: str, pixels: list[CanvasPixel], force: bool
    ) -> SendMessageResult:
        """Publish the drawing, or refuse it in the discussion phase or off the round channels.

        Raises ``ValueError`` for pixels that do not make a drawing on this
        canvas, which reaches the viewer as the tool's error.
        """
        runtime = self._get_runtime()
        if self._in_postmortem():
            return _rejected(detail=DRAWING_REFUSED_IN_DISCUSSION, runtime=runtime)
        if channel_id not in self._link_channel_ids and not channel_id.startswith(
            DIRECT_CHANNEL_PREFIX
        ):
            return _rejected(detail=DRAWING_REFUSED_ON_CHANNEL, runtime=runtime)
        try:
            drawing = CanvasDrawing(width=self._width, height=self._height, pixels=pixels)
        except ValidationError as error:
            raise ValueError(_drawing_error(error=error)) from error
        return await runtime.publish_drawing(
            agent_id=agent_id, channel_id=channel_id, drawing=drawing, force=force
        )


def _rejected(detail: str, runtime: ScenarioRuntimeHandle) -> SendMessageResult:
    """A refused drawing, with the reason the viewer reads."""
    return SendMessageResult(
        status=SendStatus.REJECTED,
        detail=detail,
        new_messages=[],
        token_count=0,
        current_round=runtime.current_round,
        message_id=None,
    )


def _drawing_error(error: ValidationError) -> str:
    """The reasons ``pixels`` do not make a drawing, as one line per problem."""
    return "; ".join(str(detail["msg"]) for detail in error.errors())
