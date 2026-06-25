"""Per-message gzip compression ratio.

A model-free, deterministic compressibility measure: the ratio of a message's
gzip-compressed size to its original size, in bytes. Lower means more
compressible/repetitive (gzip exploits repeated substrings and codes). Shared by
the ``gzip_compression_ratio`` metric and the veyru spreadsheet exporters.

Caveat: gzip carries ~18 bytes of fixed header/footer overhead, so for short
messages the ratio routinely exceeds 1.0 (the compressed output is larger than
the input). The signal is meaningful in aggregate (means over many messages),
not in individual short-message values.
"""

import gzip
import math

_COMPRESS_LEVEL = 9


def gzip_compression_ratio(text: str) -> float:
    """Return ``len(gzip(text)) / len(text)`` in bytes (compressed/original).

    Both sizes are UTF-8 byte counts. Returns ``nan`` for empty text (no bytes to
    compress), so callers can drop it like the other per-message scores rather than
    serialize a misleading value.
    """
    if not text:
        return math.nan
    data = text.encode("utf-8")
    compressed = gzip.compress(data, compresslevel=_COMPRESS_LEVEL)
    return len(compressed) / len(data)
