"""Canvas drawings: what makes one valid, the image a recipient sees, and that image in history.

A drawing reaches its recipient as a PNG attached to a tool result. The runner
sends the result as its JSON followed by labelled images, the event log records
the two apart, and the history rebuild and the history cleanup put them back
together. These tests pin each step.
"""

import io
import json

import pytest
from PIL import Image
from pydantic import ValidationError
from pydantic_ai.messages import (
    BinaryContent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)

from glossogen.models.canvas import PNG_MEDIA_TYPE, CanvasDrawing, CanvasPixel, ToolResultImage
from glossogen.models.mcp_responses import ChannelMessage, ReadChannelResult
from glossogen.run_replay.tool_return_images import split_tool_return, tool_return_with_images
from glossogen.runners.history_cleanup_processor import clean_history
from glossogen.runtime.canvas_rendering import block_size_px, render_drawing_png


def drawing(pixels: list[tuple[int, int]]) -> CanvasDrawing:
    """A drawing on a 4x3 canvas painting ``pixels``."""
    return CanvasDrawing(width=4, height=3, pixels=[CanvasPixel(x=x, y=y) for x, y in pixels])


def test_a_drawing_counts_its_painted_pixels() -> None:
    assert drawing(pixels=[(0, 0), (3, 2), (1, 1)]).pixel_count == 3


@pytest.mark.parametrize(
    ("pixels", "reason"),
    [
        ([(4, 0)], "outside the 4x3 canvas"),
        ([(0, 3)], "outside the 4x3 canvas"),
        ([(1, 1), (1, 1)], "listed more than once"),
        ([], "at least 1 item"),
    ],
)
def test_a_drawing_refuses_pixels_it_cannot_paint(
    pixels: list[tuple[int, int]], reason: str
) -> None:
    with pytest.raises(ValidationError, match=reason):
        drawing(pixels=pixels)


def test_the_image_paints_exactly_the_listed_pixels_black() -> None:
    painted = drawing(pixels=[(0, 0), (3, 2)])
    image = Image.open(io.BytesIO(render_drawing_png(drawing=painted))).convert("RGB")
    block = block_size_px(drawing=painted)

    assert image.size == (4 * block + 1, 3 * block + 1)

    def centre(x: int, y: int) -> tuple[int, int, int]:
        pixel = image.getpixel((x * block + block // 2, y * block + block // 2))
        assert isinstance(pixel, tuple)
        return (int(pixel[0]), int(pixel[1]), int(pixel[2]))

    for y in range(3):
        for x in range(4):
            expected = (255, 255, 255)
            if (x, y) in {(0, 0), (3, 2)}:
                expected = (0, 0, 0)
            assert centre(x=x, y=y) == expected, (x, y)


def test_an_image_survives_its_base64_record() -> None:
    data = render_drawing_png(drawing=drawing(pixels=[(1, 2)]))
    image = ToolResultImage.from_bytes(number=1, media_type=PNG_MEDIA_TYPE, data=data)

    recorded = ToolResultImage.model_validate(json.loads(image.model_dump_json()))

    assert recorded.data == data


def image(number: int) -> ToolResultImage:
    """Image ``number``: a drawing with one pixel in column ``number - 1``."""
    return ToolResultImage.from_bytes(
        number=number,
        media_type=PNG_MEDIA_TYPE,
        data=render_drawing_png(drawing=drawing(pixels=[(number - 1, 0)])),
    )


def test_content_with_images_splits_back_into_its_text_and_images() -> None:
    images = [image(number=1), image(number=2)]

    content = tool_return_with_images(text='{"a": 1}', images=images)
    split = split_tool_return(content=content)

    assert content[1] == "Image 1:"
    assert isinstance(content[2], BinaryContent)
    assert split is not None
    assert split.text == '{"a": 1}'
    assert split.images == images


def test_plain_content_does_not_split() -> None:
    assert split_tool_return(content='{"a": 1}') is None
    assert split_tool_return(content={"a": 1}) is None


def read_with_drawings(messages: list[tuple[str, int | None]]) -> object:
    """A ``read_channel`` result's content: ``(text, image number)`` per message."""
    result = ReadChannelResult(
        current_round=1,
        messages=[
            ChannelMessage(
                round=1, sender="Viewer 1", text=text, elapsed_seconds=float(index), image=number
            )
            for index, (text, number) in enumerate(messages)
        ],
    )
    numbers = [number for _, number in messages if number is not None]
    return tool_return_with_images(
        text=json.dumps(result.model_dump()), images=[image(number=n) for n in numbers]
    )


def two_reads(first: object, second: object) -> list[ModelMessage]:
    """Two read_channel calls on the link and their results."""
    history: list[ModelMessage] = []
    for call_id, content in (("first", first), ("second", second)):
        history.append(
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="read_channel",
                        args={"channel_id": "link_a", "last_n": 10},
                        tool_call_id=call_id,
                    )
                ]
            )
        )
        history.append(
            ModelRequest(
                parts=[
                    ToolReturnPart(tool_name="read_channel", content=content, tool_call_id=call_id)
                ]
            )
        )
    history.append(ModelResponse(parts=[TextPart(content="done")]))
    return history


def test_a_drawing_read_twice_keeps_its_image_only_in_the_first_read() -> None:
    first = read_with_drawings(messages=[("", 1)])
    second = read_with_drawings(messages=[("", 1), ("", 2)])

    history = two_reads(first=first, second=second)
    cleaned = clean_history(messages=history)

    second_request = cleaned[3]
    assert isinstance(second_request, ModelRequest)
    part = second_request.parts[0]
    assert isinstance(part, ToolReturnPart)
    split = split_tool_return(content=part.content)
    assert split is not None
    kept = json.loads(split.text)["messages"]
    assert [entry["image"] for entry in kept] == [2]
    assert [kept_image.number for kept_image in split.images] == [2]
    assert cleaned[1] is history[1]


def test_a_text_message_has_no_image_field_in_what_the_agent_reads() -> None:
    message = ChannelMessage(round=1, sender="Viewer 1", text="hi", elapsed_seconds=1.0)

    assert "image" not in message.model_dump()
