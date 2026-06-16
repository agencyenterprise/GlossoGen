"""Resolve run supersession chains recorded in ``runs/supersedes_map.csv``.

Baselines (and other runs) are re-run over time; each replacement is recorded as an
``old_run_id,new_run_id`` row. A run that references another run by id (e.g. a derived
run's ``src=``) points at whichever id was current when it ran, so consumers must follow
this map to the head-of-chain (current) run.
"""

import csv
from pathlib import Path


def load_supersession_one_step(runs_dir: Path) -> dict[str, str]:
    """Read ``supersedes_map.csv`` into a one-step ``old_run_id -> new_run_id`` map.

    Returns an empty map when the file is absent.
    """
    path = runs_dir / "supersedes_map.csv"
    if not path.exists():
        return {}
    one_step: dict[str, str] = {}
    with path.open() as handle:
        for row in csv.DictReader(handle):
            old_id = row.get("old_run_id")
            new_id = row.get("new_run_id")
            if not old_id:
                continue
            if not new_id:
                continue
            one_step[old_id] = new_id
    return one_step


def resolve_head(run_id: str, one_step: dict[str, str]) -> str:
    """Follow the supersession chain from ``run_id`` to its current head (cycle-safe)."""
    seen = set()
    while run_id in one_step and run_id not in seen:
        seen.add(run_id)
        run_id = one_step[run_id]
    return run_id
