"""Reading a child process's output stream up to a byte limit without blocking the child."""

import asyncio
from typing import NamedTuple

READ_CHUNK_BYTES = 65536


class CappedRead(NamedTuple):
    """What one stream gave: the bytes kept, and whether more were dropped."""

    kept: bytes
    cut: bool


async def read_capped(stream: asyncio.StreamReader, limit: int) -> CappedRead:
    """Read ``stream`` to its end, keeping the first ``limit`` bytes.

    Past the limit the rest is read and dropped, so the child is never blocked on a
    full pipe.
    """
    kept = bytearray()
    over = False
    while True:
        chunk = await stream.read(READ_CHUNK_BYTES)
        if not chunk:
            return CappedRead(kept=bytes(kept), cut=over)
        if over:
            continue
        room = limit - len(kept)
        if len(chunk) > room:
            kept.extend(chunk[:room])
            over = True
        else:
            kept.extend(chunk)
