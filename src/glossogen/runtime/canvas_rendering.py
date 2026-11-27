"""Renders a canvas drawing as the PNG image its recipient sees.

Each canvas pixel becomes a square block, sized so that the longer side of the
image is close to ``TARGET_IMAGE_SIDE_PX``. Painted pixels are black on white.
Thin grey lines separate the blocks, so a reader can count rows and columns.
The image carries no coordinates or labels.
"""

import io

from PIL import Image, ImageDraw

from glossogen.models.canvas import CanvasDrawing

TARGET_IMAGE_SIDE_PX = 512
MIN_BLOCK_PX = 4
_BACKGROUND = (255, 255, 255)
_INK = (0, 0, 0)
_GRID_LINE = (200, 200, 200)


def block_size_px(drawing: CanvasDrawing) -> int:
    """The side of the square block one canvas pixel becomes, in image pixels."""
    return max(MIN_BLOCK_PX, TARGET_IMAGE_SIDE_PX // max(drawing.width, drawing.height))


def render_drawing_png(drawing: CanvasDrawing) -> bytes:
    """``drawing`` as a PNG: black painted blocks on white, separated by grey grid lines."""
    block = block_size_px(drawing=drawing)
    width_px = drawing.width * block + 1
    height_px = drawing.height * block + 1
    image = Image.new(mode="RGB", size=(width_px, height_px), color=_BACKGROUND)
    draw = ImageDraw.Draw(image)
    for pixel in drawing.pixels:
        left = pixel.x * block
        top = pixel.y * block
        draw.rectangle(xy=(left, top, left + block, top + block), fill=_INK)
    for column in range(drawing.width + 1):
        x = column * block
        draw.line(xy=(x, 0, x, height_px - 1), fill=_GRID_LINE, width=1)
    for row in range(drawing.height + 1):
        y = row * block
        draw.line(xy=(0, y, width_px - 1, y), fill=_GRID_LINE, width=1)
    buffer = io.BytesIO()
    image.save(fp=buffer, format="PNG")
    return buffer.getvalue()
