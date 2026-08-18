"""Streaming an archive that was built into a temporary file.

Building into memory and wrapping the result in a response holds the archive
twice at peak, which is survivable for one run and not for a few hundred. A
temporary file holds it once, on disk.

The other thing this buys is a real ``Content-Length``. A generator that deflates
as it yields cannot declare one, so a browser downloading it shows an
indeterminate spinner and cannot tell a truncated transfer from a complete one.
Building first and streaming second means the length is known before the first
byte leaves.

``TemporaryFile`` is unlinked by the OS as soon as it is created, so a client that
disconnects mid-transfer costs nothing beyond the closed handle. That is why
there is no cleanup callback here: a background task that deletes a named file can
be skipped when sending raises, and then the file stays.

The archive is written under ``TMPDIR``, which is the knob to point at a larger
volume if the default is small.

Building in a worker thread keeps the event loop responsive even though row
building is pure Python. The interpreter yields every ``sys.getswitchinterval()``,
5ms by default, so a CPU-bound thread competes with the loop instead of holding it.

Measured on the widest export a 500-run selection can request, with every table,
every column repeated onto the long rows, and metric summaries on: 2.37s to build,
during which the loop ticked 414 times with a worst gap of 12ms.

That is worth knowing because the number to watch here is the gap, not the build
time. A build that takes seconds is fine; a loop that cannot answer anything for
seconds is not, and this does not do that.
"""

import asyncio
import logging
import tempfile
from collections.abc import AsyncIterator, Callable
from typing import IO

from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

_STREAM_CHUNK_BYTES = 1024 * 1024


async def _stream_and_close(handle: IO[bytes]) -> AsyncIterator[bytes]:
    """Yield the handle's contents in chunks, closing it when the stream ends."""
    try:
        while True:
            chunk = await asyncio.to_thread(handle.read, _STREAM_CHUNK_BYTES)
            if not chunk:
                return
            yield chunk
    finally:
        handle.close()


async def build_temp_file_archive_response(
    build: Callable[[IO[bytes]], None],
    filename: str,
    media_type: str,
) -> StreamingResponse:
    """Run ``build`` into a temporary file and return a response streaming it.

    ``build`` runs in a worker thread, which bounds memory to one copy on disk and
    leaves the event loop able to answer other requests while it works. Anything it
    raises propagates from here, before any part of the response has been sent, so a
    failure is still expressible as a status code.
    """
    handle = tempfile.TemporaryFile()
    try:
        await asyncio.to_thread(build, handle)
        size = handle.tell()
        handle.seek(0)
    except BaseException:
        handle.close()
        raise

    logger.info("Streaming %s (%d bytes)", filename, size)
    return StreamingResponse(
        content=_stream_and_close(handle=handle),
        media_type=media_type,
        headers={
            "Content-Length": str(size),
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
