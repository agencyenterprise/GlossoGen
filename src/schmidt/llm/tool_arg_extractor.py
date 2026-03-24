"""Incremental extractor for send_message tool call arguments.

Parses the streaming JSON fragments from the Claude API to extract
``channel_id`` and ``text`` values as they arrive, enabling real-time
message preview in the frontend.
"""

import re
from typing import NamedTuple

# Matches JSON string escape sequences
_ESCAPE_RE = re.compile(r'\\(["\\\/bfnrt]|u[0-9a-fA-F]{4})')

_SIMPLE_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}


def _unescape_json_char(match: re.Match[str]) -> str:
    """Convert a single JSON escape sequence to its character."""
    seq = match.group(1)
    if seq.startswith("u"):
        return chr(int(seq[1:], 16))
    return _SIMPLE_ESCAPES.get(seq, seq)


class ExtractorResult(NamedTuple):
    """Result of feeding a chunk to the extractor."""

    channel_id: str | None
    new_text: str


class SendMessageTextExtractor:
    """Incrementally extracts channel_id and text from streaming send_message JSON.

    The Claude API streams tool call arguments as partial JSON fragments via
    ``input_json_delta`` events. This extractor tracks the accumulated JSON
    buffer and yields the ``channel_id`` and new characters from the ``text``
    field as they arrive.

    Field order is not guaranteed — ``text`` may appear before ``channel_id``.
    Text is buffered internally until ``channel_id`` is available, then emitted
    in a batch on the next ``feed()`` call.
    """

    def __init__(self) -> None:
        """Initialize the extractor with empty state."""
        self._buffer = ""
        self._channel_id: str | None = None
        self._text_value_start: int | None = None
        self._last_emitted_pos: int = 0
        self._buffered_text = ""

    @property
    def channel_id(self) -> str | None:
        """The extracted channel_id, or None if not yet found."""
        return self._channel_id

    def feed(self, accumulated_json: str) -> ExtractorResult:
        """Process the full accumulated JSON and return any new extractable text.

        Args:
            accumulated_json: The complete JSON accumulated so far (not a delta).

        Returns:
            ExtractorResult with channel_id and new_text. channel_id is None
            until the value is fully parsed. new_text contains characters
            added since the last call.
        """
        self._buffer = accumulated_json

        # Try to extract channel_id if not yet found
        if self._channel_id is None:
            self._channel_id = self._extract_string_value("channel_id")

        # Try to find where the text value starts
        if self._text_value_start is None:
            self._text_value_start = self._find_value_start("text")
            if self._text_value_start is not None:
                self._last_emitted_pos = self._text_value_start

        # Extract new text characters
        new_text = ""
        if self._text_value_start is not None:
            raw = self._extract_partial_string_value(self._text_value_start)
            if len(raw) > self._last_emitted_pos - self._text_value_start:
                new_chars = raw[self._last_emitted_pos - self._text_value_start :]
                self._last_emitted_pos = self._text_value_start + len(raw)

                if self._channel_id is not None:
                    # Emit any previously buffered text plus new chars
                    new_text = self._buffered_text + new_chars
                    self._buffered_text = ""
                else:
                    # Buffer until channel_id is known
                    self._buffered_text += new_chars

        return ExtractorResult(channel_id=self._channel_id, new_text=new_text)

    def _find_value_start(self, key: str) -> int | None:
        """Find the byte position where a JSON string value begins (after the opening quote)."""
        # Look for "key": " or "key":" patterns
        for pattern in [f'"{key}": "', f'"{key}":"']:
            idx = self._buffer.find(pattern)
            if idx != -1:
                return idx + len(pattern)
        return None

    def _extract_string_value(self, key: str) -> str | None:
        """Extract a complete JSON string value for the given key, or None if incomplete."""
        start = self._find_value_start(key)
        if start is None:
            return None

        # Walk forward to find the closing unescaped quote
        i = start
        while i < len(self._buffer):
            ch = self._buffer[i]
            if ch == "\\":
                i += 2  # Skip escape sequence
                continue
            if ch == '"':
                raw = self._buffer[start:i]
                return _ESCAPE_RE.sub(_unescape_json_char, raw)
            i += 1

        return None  # String not yet complete

    def _extract_partial_string_value(self, start: int) -> str:
        """Extract characters from a possibly-incomplete JSON string value.

        Returns all unescaped characters from position ``start`` up to either
        the closing quote or the end of the buffer (whichever comes first).
        Incomplete escape sequences at the buffer tail are excluded.
        """
        result: list[str] = []
        i = start
        while i < len(self._buffer):
            ch = self._buffer[i]
            if ch == '"':
                break
            if ch == "\\":
                if i + 1 >= len(self._buffer):
                    break  # Incomplete escape at end — wait for more data
                escaped = self._buffer[i : i + 2]
                match = _ESCAPE_RE.match(escaped)
                if match:
                    result.append(_unescape_json_char(match))
                    i += len(match.group(0))
                else:
                    # Might be a unicode escape that's not complete yet
                    if self._buffer[i + 1] == "u" and i + 6 > len(self._buffer):
                        break  # Wait for more data
                    result.append(self._buffer[i + 1])
                    i += 2
                continue
            result.append(ch)
            i += 1
        return "".join(result)
