"""A drawing an agent sends on a canvas, and the image a tool result carries.

A ``CanvasDrawing`` is a set of painted pixels on a canvas of a fixed width and
height. The sender names each pixel by its column ``x`` and row ``y``, counted
from 0 at the top left. The recipient never reads the coordinates: it receives
the drawing rendered as an image (``ToolResultImage``), attached to the result
of the tool that delivered the message.
"""

import base64
from typing import Self

from pydantic import BaseModel, Field, model_validator

PNG_MEDIA_TYPE = "image/png"


class CanvasPixel(BaseModel):
    """One painted pixel: its column ``x`` and row ``y``, from 0 at the top left."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)


class CanvasDrawing(BaseModel):
    """The pixels one message paints on a ``width`` x ``height`` canvas.

    A drawing paints at least one pixel, each pixel inside the canvas, and no
    pixel twice.
    """

    width: int = Field(gt=0)
    height: int = Field(gt=0)
    pixels: list[CanvasPixel] = Field(min_length=1)

    @model_validator(mode="after")
    def _pixels_inside_and_distinct(self) -> Self:
        seen: set[tuple[int, int]] = set()
        for pixel in self.pixels:
            if pixel.x >= self.width or pixel.y >= self.height:
                raise ValueError(
                    f"pixel ({pixel.x}, {pixel.y}) is outside the {self.width}x{self.height} "
                    f"canvas: x runs from 0 to {self.width - 1} and y from 0 to {self.height - 1}"
                )
            if (pixel.x, pixel.y) in seen:
                raise ValueError(f"pixel ({pixel.x}, {pixel.y}) is listed more than once")
            seen.add((pixel.x, pixel.y))
        return self

    @property
    def pixel_count(self) -> int:
        """How many pixels the drawing paints."""
        return len(self.pixels)


class ToolResultImage(BaseModel):
    """An image attached to a tool result, numbered as the result's text refers to it.

    ``data_base64`` holds the encoded image as base64, which is how a run's
    event log records it.
    """

    number: int = Field(ge=1)
    media_type: str
    data_base64: str

    @classmethod
    def from_bytes(cls, number: int, media_type: str, data: bytes) -> Self:
        """An image from its encoded bytes."""
        return cls(
            number=number, media_type=media_type, data_base64=base64.b64encode(data).decode()
        )

    @property
    def data(self) -> bytes:
        """The encoded image."""
        return base64.b64decode(self.data_base64)
