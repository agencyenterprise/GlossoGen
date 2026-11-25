"""Schema and reader for ``history_transfer_manifest.json``.

A history-transfer run is a fresh run in which some agents start with the history
an agent built in another finished run, which may be of another scenario. The
manifest names the source run, the round its history was cut at, and which agent
of the source each transferred seat carries. Each seat's history, ending in the
message that opens the new run, is saved beside the manifest as written at launch,
so a resumed run hands the agent the same history.

``run_derivation/history_transfer.py`` writes it. Resume and the protocol probes
read it through ``run_replay/`` without importing ``run_derivation/``. The fork
flows check for it to refuse a history-transfer run as a source, and the seat checks
read it to refuse a transferred seat as a source agent.
"""

from pathlib import Path

from pydantic import BaseModel

HISTORY_TRANSFER_MANIFEST_FILENAME = "history_transfer_manifest.json"


class TransferredSeat(BaseModel):
    """One seat of the new run and the source agent whose history it carries.

    ``history_file`` is the file, relative to the run directory, holding the
    seat's opening history as pydantic-ai messages.
    """

    agent_id: str
    source_agent_id: str
    source_model: str
    source_provider: str
    history_file: str


class HistoryTransferManifest(BaseModel):
    """Persisted record of a history-transfer run's source.

    ``source_round_end`` is the last source round whose events feed the
    transferred histories.
    """

    source_run_id: str
    source_run_dir: str
    source_round_end: int
    seats: list[TransferredSeat]


def transferred_history_file_name(agent_id: str) -> str:
    """The file name of ``agent_id``'s transferred history inside the run directory."""
    return f"transferred_history_{agent_id}.json"


def read_history_transfer_manifest(run_dir: Path) -> HistoryTransferManifest | None:
    """Load ``history_transfer_manifest.json`` from ``run_dir`` or return ``None``."""
    manifest_path = run_dir / HISTORY_TRANSFER_MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    return HistoryTransferManifest.model_validate_json(manifest_path.read_bytes())


def write_history_transfer_manifest(run_dir: Path, manifest: HistoryTransferManifest) -> None:
    """Write ``manifest`` to ``run_dir/history_transfer_manifest.json``."""
    manifest_path = run_dir / HISTORY_TRANSFER_MANIFEST_FILENAME
    manifest_path.write_text(manifest.model_dump_json(indent=2))
