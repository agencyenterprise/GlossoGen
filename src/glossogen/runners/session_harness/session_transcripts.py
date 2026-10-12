"""Copying an agent CLI's session transcripts out of the seat's private state.

A CLI writes its transcripts somewhere under the seat's ``harness_state``
directory, which archives and forks leave out. The transcripts are the seat's
record, so each session copies them to ``transcripts/`` beside that directory
when it closes.
"""

import shutil
from pathlib import Path

TRANSCRIPTS_DIR_NAME = "transcripts"


def keep_session_transcripts(seat_dir: Path, source_dir: Path) -> None:
    """Copy every ``*.jsonl`` under ``source_dir`` to the seat's ``transcripts/``.

    Each copy keeps its path relative to ``source_dir``, so two transcripts with
    one name in different directories are both kept. A resumed session appends
    to the transcript it started, so a later close overwrites an earlier copy
    of it.
    """
    if not source_dir.is_dir():
        return
    kept = seat_dir / TRANSCRIPTS_DIR_NAME
    for transcript in source_dir.rglob("*.jsonl"):
        destination = kept / transcript.relative_to(source_dir)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src=transcript, dst=destination)
