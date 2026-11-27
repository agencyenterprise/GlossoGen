"""A tool result with attached images, as pydantic-ai content and back.

A result that attaches images is sent to the model as a list: the result's text
first, then for each image a label ``Image <number>:`` followed by the image
itself. The runner builds that list, the event log records the text and the
images apart, and the history rebuild and the history cleanup turn them back
into the same list.
"""

import re
from collections.abc import Sequence
from typing import NamedTuple

from pydantic_ai.messages import BinaryContent

from glossogen.models.canvas import ToolResultImage

_LABEL_PATTERN = re.compile(r"Image (\d+):")

ToolReturnWithImages = list[str | BinaryContent]


class SplitToolReturn(NamedTuple):
    """A tool result's text and the images attached to it."""

    text: str
    images: list[ToolResultImage]


def image_label(number: int) -> str:
    """The label sent to the model just before image ``number``."""
    return f"Image {number}:"


def tool_return_with_images(text: str, images: Sequence[ToolResultImage]) -> ToolReturnWithImages:
    """The content a model receives for a result with ``text`` and ``images`` attached."""
    content: ToolReturnWithImages = [text]
    for image in images:
        content.append(image_label(number=image.number))
        content.append(BinaryContent(data=image.data, media_type=image.media_type))
    return content


def split_tool_return(content: object) -> SplitToolReturn | None:
    """The text and images of content built by ``tool_return_with_images``, or ``None``.

    Returns ``None`` for content of any other shape, such as plain text or a
    mapping.
    """
    if not isinstance(content, list) or not content:
        return None
    items: list[object] = list(content)  # pyright: ignore[reportUnknownArgumentType]
    text = items[0]
    rest = items[1:]
    if not isinstance(text, str) or len(rest) % 2 != 0:
        return None
    images: list[ToolResultImage] = []
    for label, image in zip(rest[::2], rest[1::2], strict=True):
        if not isinstance(label, str) or not isinstance(image, BinaryContent):
            return None
        matched = _LABEL_PATTERN.fullmatch(label)
        if matched is None:
            return None
        images.append(
            ToolResultImage.from_bytes(
                number=int(matched.group(1)), media_type=image.media_type, data=image.data
            )
        )
    return SplitToolReturn(text=text, images=images)
