"""Choosing where this server's label descriptions live.

The same test the run lookup and the dashboard store use: a pool means Postgres, no
pool means the filesystem. Nothing above this line knows which one answered.
"""

from pathlib import Path

from fastapi import Request

from glossogen.label_descriptions.filesystem_label_description_store import (
    FilesystemLabelDescriptionStore,
)
from glossogen.label_descriptions.label_description_store import LabelDescriptionStore
from glossogen.label_descriptions.postgres_label_description_store import (
    PostgresLabelDescriptionStore,
)


def label_description_store_for(request: Request) -> LabelDescriptionStore:
    """Return the store backing this server's label descriptions."""
    pool = request.app.state.db_pool
    if pool is None:
        runs_dir: Path = request.app.state.runs_dir
        return FilesystemLabelDescriptionStore(runs_dir=runs_dir)
    return PostgresLabelDescriptionStore(pool=pool)
