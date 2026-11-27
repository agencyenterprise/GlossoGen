"""The ``send_drawing`` tool a scenario offers its agents under the canvas medium.

An agent lists the pixels to paint on the run's canvas. The drawing goes on its
team's link channel, or with one-to-one addressing to one named teammate, and
the runtime delivers it to the recipients as an image. A drawing is refused in
the discussion phase and on any channel other than a link or a direct channel.
"""

from collections.abc import Awaitable, Callable

from pydantic import ValidationError

from glossogen.engine.canvas_link import (
    DRAWING_REFUSED_IN_DISCUSSION,
    DRAWING_REFUSED_ON_CHANNEL,
    SEND_DRAWING_TOOL,
    send_drawing_description,
)
from glossogen.models.canvas import CanvasDrawing, CanvasPixel
from glossogen.models.channel import DIRECT_CHANNEL_PREFIX
from glossogen.models.mcp_responses import SendMessageResult, SendStatus
from glossogen.scenario_contract.scenario_base import ScenarioRuntimeHandle
from glossogen.scenario_contract.scenario_tool import ScenarioTool

MAX_CANVAS_SIDE = 256
"""The widest or tallest canvas a scenario's knobs accept."""

ChannelForRecipient = Callable[[str, str], Awaitable[str]]
"""Turns ``(agent_id, to)`` into the channel a one-to-one message reaches."""


class DrawingSender:
    """Posts agents' drawings on a ``width`` x ``height`` canvas through the runtime.

    ``link_channel_ids`` are the channels a drawing may go on besides direct
    channels.
    """

    def __init__(
        self,
        width: int,
        height: int,
        link_channel_ids: frozenset[str],
        in_postmortem: Callable[[], bool],
        get_runtime: Callable[[], ScenarioRuntimeHandle],
    ) -> None:
        self._width = width
        self._height = height
        self._link_channel_ids = link_channel_ids
        self._in_postmortem = in_postmortem
        self._get_runtime = get_runtime

    def link_tool(self) -> ScenarioTool:
        """The ``send_drawing`` tool that posts on a channel the agent names."""
        return ScenarioTool(
            name=SEND_DRAWING_TOOL,
            description=send_drawing_description(
                width=self._width, height=self._height, one_to_one=False
            ),
            executor=self.draw_on_channel,
        )

    def teammate_tool(self, channel_for_recipient: ChannelForRecipient) -> ScenarioTool:
        """The ``send_drawing`` tool that posts to one teammate, named by ``to``."""

        async def draw_to_teammate(
            agent_id: str, to: str, pixels: list[CanvasPixel], force: bool
        ) -> SendMessageResult:
            channel_id = await channel_for_recipient(agent_id, to)
            return await self._send(
                agent_id=agent_id, channel_id=channel_id, pixels=pixels, force=force
            )

        return ScenarioTool(
            name=SEND_DRAWING_TOOL,
            description=send_drawing_description(
                width=self._width, height=self._height, one_to_one=True
            ),
            executor=draw_to_teammate,
        )

    async def draw_on_channel(
        self, agent_id: str, channel_id: str, pixels: list[CanvasPixel], force: bool
    ) -> SendMessageResult:
        """Post a drawing of ``pixels`` on ``channel_id``."""
        return await self._send(
            agent_id=agent_id, channel_id=channel_id, pixels=pixels, force=force
        )

    async def _send(
        self, agent_id: str, channel_id: str, pixels: list[CanvasPixel], force: bool
    ) -> SendMessageResult:
        """Publish the drawing, or refuse it in the discussion phase or off the round channels.

        Raises ``ValueError`` for pixels that do not make a drawing on this
        canvas, which reaches the agent as the tool's error.
        """
        runtime = self._get_runtime()
        if self._in_postmortem():
            return rejected_send(
                detail=DRAWING_REFUSED_IN_DISCUSSION, current_round=runtime.current_round
            )
        if channel_id not in self._link_channel_ids and not channel_id.startswith(
            DIRECT_CHANNEL_PREFIX
        ):
            return rejected_send(
                detail=DRAWING_REFUSED_ON_CHANNEL, current_round=runtime.current_round
            )
        try:
            drawing = CanvasDrawing(width=self._width, height=self._height, pixels=pixels)
        except ValidationError as error:
            raise ValueError(_drawing_error(error=error)) from error
        return await runtime.publish_drawing(
            agent_id=agent_id, channel_id=channel_id, drawing=drawing, force=force
        )


def rejected_send(detail: str, current_round: int) -> SendMessageResult:
    """A refused send, with the reason the agent reads."""
    return SendMessageResult(
        status=SendStatus.REJECTED,
        detail=detail,
        new_messages=[],
        token_count=0,
        current_round=current_round,
        message_id=None,
    )


def _drawing_error(error: ValidationError) -> str:
    """The reasons ``pixels`` do not make a drawing, as one line per problem."""
    return "; ".join(str(detail["msg"]) for detail in error.errors())
