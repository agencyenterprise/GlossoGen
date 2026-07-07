"""Per-message DEFLATE compression ratio (gzip's codec, framing excluded).

A model-free, deterministic compressibility measure: the ratio of a message's
raw-DEFLATE-compressed size to its original size, in bytes. DEFLATE is the
compression algorithm gzip uses; we run it *without* the gzip wrapper so the
constant 18-byte header/footer (10-byte header + 8-byte footer) does not inflate
the ratio. ``len(raw_deflate(text))`` equals ``len(gzip(text)) - 18`` exactly, so
this is precisely "gzip compression ratio with the fixed framing removed".

Lower means more compressible/repetitive (DEFLATE exploits repeated substrings
and codes). Shared by the ``gzip_compression_ratio`` metric and the veyru
spreadsheet exporters.

DEFLATE still carries a small per-stream overhead (block header + Huffman/stored
framing), so the very shortest or incompressible messages can read slightly above
1.0; the signal is most meaningful in aggregate.
"""

import math
import zlib

_COMPRESS_LEVEL = 9
_RAW_DEFLATE_WBITS = -15


def gzip_compression_ratio(text: str) -> float:
    """Return ``len(raw_deflate(text)) / len(text)`` in bytes (compressed/original).

    Uses raw DEFLATE (``wbits=-15``) so the constant gzip header/footer is excluded.
    Both sizes are UTF-8 byte counts. Returns ``nan`` for empty text (no bytes to
    compress), so callers can drop it like the other per-message scores.
    """
    if not text:
        return math.nan
    data = text.encode("utf-8")
    compressor = zlib.compressobj(_COMPRESS_LEVEL, zlib.DEFLATED, _RAW_DEFLATE_WBITS)
    compressed = compressor.compress(data) + compressor.flush()
    return len(compressed) / len(data)
