"""The ``protocol_agreement`` metric's sidecar in a run directory: its path and its reader."""

import logging
from pathlib import Path

import aiofiles
from pydantic import ValidationError

from glossogen.models.protocol_agreement import ProtocolAgreementReport

logger = logging.getLogger(__name__)

PROTOCOL_AGREEMENT_FILE_NAME = "protocol_agreement.json"


def protocol_agreement_path(run_dir: Path) -> Path:
    """Return the run's ``protocol_agreement.json``."""
    return run_dir / PROTOCOL_AGREEMENT_FILE_NAME


async def read_protocol_agreement(run_dir: Path) -> ProtocolAgreementReport | None:
    """Return the run's protocol-agreement sidecar, or ``None`` when it is absent or unreadable.

    An unreadable file is logged and treated as absent, so it costs the run this panel
    rather than failing the request.
    """
    path = protocol_agreement_path(run_dir=run_dir)
    if not path.is_file():
        return None
    try:
        async with aiofiles.open(path, mode="r", encoding="utf-8") as handle:
            raw = await handle.read()
        return ProtocolAgreementReport.model_validate_json(raw)
    except OSError, ValidationError:
        logger.exception("Skipping unreadable protocol-agreement sidecar %s", path)
        return None
