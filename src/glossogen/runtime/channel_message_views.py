"""Stored channel messages as an agent reads them in a tool result.

``read_channel`` and a held ``send_message`` both list messages. A text message
is listed with its text. A drawing is listed with an empty text and the number
of the image that renders it, and the image is attached to the same result.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import NamedTuple

from glossogen.models.canvas import PNG_MEDIA_TYPE, ToolResultImage
from glossogen.models.elapsed_time import elapsed_seconds_since_start
from glossogen.models.mcp_responses import ChannelMessage
from glossogen.models.message import SimulationMessage
from glossogen.runtime.canvas_rendering import render_drawing_png


class ChannelMessageViews(NamedTuple):
    """Messages as an agent reads them, with the images of the drawings among them."""

    messages: list[ChannelMessage]
    images: list[ToolResultImage]


def channel_message_views(
    messages: Sequence[SimulationMessage], simulation_start_time: datetime
) -> ChannelMessageViews:
    """``messages`` as an agent reads them, numbering their drawings' images from 1."""
    views: list[ChannelMessage] = []
    images: list[ToolResultImage] = []
    for message in messages:
        image_number: int | None = None
        if message.drawing is not None:
            image_number = len(images) + 1
            images.append(
                ToolResultImage.from_bytes(
                    number=image_number,
                    media_type=PNG_MEDIA_TYPE,
                    data=render_drawing_png(drawing=message.drawing),
                )
            )
        views.append(
            ChannelMessage(
                round=message.round_number,
                sender=message.sender_display_name,
                text=message.text,
                elapsed_seconds=elapsed_seconds_since_start(
                    when=message.timestamp, start=simulation_start_time
                ),
                image=image_number,
            )
        )
    return ChannelMessageViews(messages=views, images=images)
