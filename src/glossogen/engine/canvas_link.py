"""What agents send on a team's task channel during a round, and what it costs.

With ``LinkMedium.TEXT`` an agent sends text with ``send_message`` and its team is
charged one unit per character. With ``LinkMedium.CANVAS`` an agent sends
drawings with ``send_drawing`` (see :mod:`glossogen.engine.drawing_sender`): it
names the pixels to paint on a canvas, its teammates receive the drawing as an
image, and its team is charged one unit per painted pixel. A scenario's
discussion phase carries text in both media.

A scenario's scoring code may count a team's charge in fields called
``characters``. Under ``CANVAS`` those fields hold pixels.
"""

from enum import StrEnum

SEND_DRAWING_TOOL = "send_drawing"


class LinkMedium(StrEnum):
    """What an agent sends on its team's task channel during a round."""

    TEXT = "text"
    CANVAS = "canvas"


def charge_unit(medium: LinkMedium) -> str:
    """The plural noun for what a team is charged under ``medium``."""
    if medium == LinkMedium.CANVAS:
        return "pixels"
    return "characters"


def charge_unit_singular(medium: LinkMedium) -> str:
    """The singular noun for one unit of what a team is charged under ``medium``."""
    if medium == LinkMedium.CANVAS:
        return "pixel"
    return "character"


def charge_unit_abbreviation(medium: LinkMedium) -> str:
    """The short unit a recorded round reason uses."""
    if medium == LinkMedium.CANVAS:
        return "pixels"
    return "chars"


TEXT_REFUSED_ON_CANVAS_LINK = (
    "During a round this run carries drawings only: send them with send_drawing. "
    "send_message is for the discussion channel."
)

DRAWING_REFUSED_IN_DISCUSSION = (
    "Drawings are for the round. In the post-round discussion phase, post text with "
    "send_message on the discussion channel."
)

DRAWING_REFUSED_ON_CHANNEL = (
    "Drawings go on your team's link channel. send_message is for the discussion channel."
)


def send_drawing_description(width: int, height: int, one_to_one: bool) -> str:
    """The ``send_drawing`` tool description for a ``width`` x ``height`` canvas."""
    if one_to_one:
        destination = (
            "Set 'to' to one teammate's agent id: only that teammate receives the drawing."
        )
    else:
        destination = (
            "Set 'channel_id' to your team's link channel: every teammate receives the drawing."
        )
    return (
        f"Send a drawing on a blank {width}x{height} canvas of white pixels. List the pixels "
        f"to paint black as [x, y] pairs, for example [[0, 0], [3, 1]]: x is the column (0 to "
        f"{width - 1}, left to right) and y the row (0 to {height - 1}, top to bottom). "
        f"{destination} The recipient sees only the "
        "image, never the coordinates. Each painted pixel is charged to your team as one "
        "unit. If new messages arrived since you last read them, the drawing is held and the "
        "new messages are returned; set force=true to send regardless."
    )
