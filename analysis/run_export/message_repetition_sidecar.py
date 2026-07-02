"""Read the ``language_repetition`` metric's per-message sidecar.

The ``language_repetition`` metric writes one JSONL row per primary-channel
message to ``language_repetition_messages.jsonl`` (an LLM-judge redundancy
factor, >= 1.0, averaged over replicas), keyed by ``message_id``. Shared by
every exporter that joins per-message repetition factors back onto its
message-level frame.
"""

import json
from pathlib import Path

_REPETITION_SIDECAR = "language_repetition_messages.jsonl"


def read_message_repetition_factors(run_dir: Path) -> dict[str, float]:
    """Map ``message_id -> per-message repetition factor`` from the metric's sidecar.

    Empty when the sidecar is absent (the run was not scored for
    ``language_repetition``).
    """
    sidecar = run_dir / _REPETITION_SIDECAR
    if not sidecar.exists():
        return {}
    factors: dict[str, float] = {}
    for line in sidecar.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        message_id = row.get("message_id")
        factor = row.get("repetition_factor")
        if isinstance(message_id, str) and isinstance(factor, (int, float)):
            factors[message_id] = float(factor)
    return factors
