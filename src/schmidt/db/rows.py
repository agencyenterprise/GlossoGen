"""Pydantic row models returned by the typed query helpers in ``queries.py``."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class GroupRow(BaseModel):
    """One row from the ``groups`` table."""

    id: UUID
    clerk_org_id: str | None
    slug: str
    name: str
    created_at: datetime


class RunRow(BaseModel):
    """One row from the ``runs`` table.

    Mirrors the on-disk run directory ``runs/{scenario}/{run_dir_name}/`` but is
    the authoritative source for tenancy: the filesystem holds no group_id.
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


class UserLastActiveGroupRow(BaseModel):
    """One row from the ``user_last_active_group`` table."""

    user_id: str
    group_id: UUID
    updated_at: datetime
