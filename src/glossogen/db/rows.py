"""Pydantic row models returned by the typed query helpers in ``queries.py``."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class GroupRow(BaseModel):
    """One row from the ``groups`` table."""

    id: UUID
    external_org_id: str | None
    slug: str
    name: str
    created_at: datetime


class RunRow(BaseModel):
    """One row from the ``runs`` table.

    Mirrors the on-disk run directory ``runs/{scenario}/{run_dir_name}/`` but is
    the authoritative source for tenancy: the filesystem holds no group_id.
    ``evaluation_content_hash`` is the digest of the run's report measurements
    at the time of the last ``PUT /evaluation``; used by
    ``glossogen sync-metadata-to-prod`` to skip PUTs for unchanged reports.
    ``labels`` mirrors the run directory's ``labels.json``, which stays the
    source of truth; ``None`` means the row has not been mirrored yet and
    readers fall back to the file.
    """

    id: int
    group_id: UUID
    scenario: str
    run_dir_name: str
    status: str
    created_at: datetime
    created_by_user_id: str | None
    source_run_scenario: str | None
    source_run_dir_name: str | None
    evaluation_content_hash: str | None
    labels: list[str] | None


class DerivedSourceCountRow(BaseModel):
    """One source run that has derived children, with the child count.

    Aggregates the ``runs`` table by ``(source_run_scenario,
    source_run_dir_name)``, the timeline parent recorded for every
    replace-agent, fork-at-round, and cross-run-replace-agent derivation.
    """

    scenario: str
    run_dir_name: str
    derived_count: int
