"""Resolving, registering and deregistering a run against the active group.

``resolve_run_or_404`` is what keeps one group's runs invisible to another: with
a database, a run directory on disk is not enough, the group must own its row.
The ``runs`` queries are replaced by an in-memory table keyed by group, so these
tests show which group each call is scoped to; the SQL itself is not exercised.
"""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, Request

from glossogen.db.rows import RunRow
from glossogen.server.identity.identity_model import Identity
from glossogen.server.runs import lookup
from glossogen.server.runs.discovery import ResolvedRun
from glossogen.server.runs.lookup import (
    deregister_run,
    get_identity,
    register_new_run,
    resolve_run_or_404,
)
from tests.fakes.db_pool import CountingPool
from tests.fakes.local_app import RUN_START, one_round_run_events, write_event_log

SCENARIO = "veyru"
RUN = "1770000100"
GROUP_A = UUID("00000000-0000-0000-0000-00000000000a")
GROUP_B = UUID("00000000-0000-0000-0000-00000000000b")


class RunKey(NamedTuple):
    group_id: UUID
    scenario: str
    run_dir_name: str


class InsertedRun(NamedTuple):
    """The arguments of one ``insert_run`` call this file checks."""

    key: RunKey
    created_by_user_id: str | None
    source_run_scenario: str | None
    source_run_dir_name: str | None
    labels: list[str]


class FakeRunsTable:
    """The ``runs`` table as a dict, behind ``get_run``, ``insert_run`` and ``delete_run``."""

    def __init__(self) -> None:
        self.rows: dict[RunKey, RunRow] = {}
        self.inserted: list[InsertedRun] = []

    def add(self, group_id: UUID, labels: list[str] | None) -> None:
        key = RunKey(group_id=group_id, scenario=SCENARIO, run_dir_name=RUN)
        self.rows[key] = RunRow(
            id=len(self.rows) + 1,
            group_id=group_id,
            scenario=SCENARIO,
            run_dir_name=RUN,
            status="completed",
            created_at=RUN_START,
            created_by_user_id=None,
            source_run_scenario=None,
            source_run_dir_name=None,
            evaluation_content_hash=None,
            labels=labels,
        )

    async def get_run(
        self,
        conn: object,  # noqa: ARG002 — signature-required
        group_id: UUID,
        scenario: str,
        run_dir_name: str,
    ) -> RunRow | None:
        return self.rows.get(
            RunKey(group_id=group_id, scenario=scenario, run_dir_name=run_dir_name)
        )

    async def insert_run(  # noqa: PLR0913 — mirrors the query's signature
        self,
        conn: object,  # noqa: ARG002 — signature-required
        group_id: UUID,
        scenario: str,
        run_dir_name: str,
        status: str,  # noqa: ARG002 — signature-required
        created_at: datetime,  # noqa: ARG002 — signature-required
        created_by_user_id: str | None,
        source_run_scenario: str | None,
        source_run_dir_name: str | None,
        labels: list[str],
    ) -> None:
        self.inserted.append(
            InsertedRun(
                key=RunKey(group_id=group_id, scenario=scenario, run_dir_name=run_dir_name),
                created_by_user_id=created_by_user_id,
                source_run_scenario=source_run_scenario,
                source_run_dir_name=source_run_dir_name,
                labels=labels,
            )
        )

    async def delete_run(
        self,
        conn: object,  # noqa: ARG002 — signature-required
        group_id: UUID,
        scenario: str,
        run_dir_name: str,
    ) -> None:
        self.rows.pop(RunKey(group_id=group_id, scenario=scenario, run_dir_name=run_dir_name), None)


@pytest.fixture
def runs_table(monkeypatch: pytest.MonkeyPatch) -> FakeRunsTable:
    table = FakeRunsTable()
    monkeypatch.setattr(target=lookup, name="get_run", value=table.get_run)
    monkeypatch.setattr(target=lookup, name="insert_run", value=table.insert_run)
    monkeypatch.setattr(target=lookup, name="delete_run", value=table.delete_run)
    return table


def request_as(
    runs_dir: Path, pool: CountingPool | None, group_id: UUID, is_local_mode: bool
) -> Request:
    """A request from user ``researcher`` in ``group_id``, to an app over ``runs_dir``."""
    db_pool = None
    if pool is not None:
        db_pool = pool.as_db_pool()
    app = SimpleNamespace(state=SimpleNamespace(runs_dir=runs_dir, db_pool=db_pool))
    request = Request(scope={"type": "http", "method": "GET", "headers": [], "app": app})
    request.state.identity = Identity(
        user_id="researcher", active_group_id=group_id, is_local_mode=is_local_mode
    )
    return request


def write_run(runs_dir: Path) -> Path:
    return write_event_log(
        runs_dir=runs_dir,
        scenario_name=SCENARIO,
        run_dir_name=RUN,
        events=one_round_run_events(scenario_name=SCENARIO, run_dir_name=RUN, finished=True),
        extra_records=[],
    )


async def resolve(request: Request) -> ResolvedRun:
    return await resolve_run_or_404(request=request, scenario=SCENARIO, run_dir_name=RUN)


# --- resolving ------------------------------------------------------------------


async def test_another_groups_run_is_not_found_even_with_its_files_on_disk(
    tmp_path: Path, runs_table: FakeRunsTable
) -> None:
    write_run(runs_dir=tmp_path)
    runs_table.add(group_id=GROUP_A, labels=[])

    with pytest.raises(HTTPException) as raised:
        await resolve(
            request_as(
                runs_dir=tmp_path, pool=CountingPool(), group_id=GROUP_B, is_local_mode=False
            )
        )

    assert raised.value.status_code == 404


async def test_the_owning_group_resolves_the_run_with_its_mirrored_labels(
    tmp_path: Path, runs_table: FakeRunsTable
) -> None:
    run_dir = write_run(runs_dir=tmp_path)
    runs_table.add(group_id=GROUP_A, labels=["baseline_oss"])

    resolved = await resolve(
        request_as(runs_dir=tmp_path, pool=CountingPool(), group_id=GROUP_A, is_local_mode=False)
    )

    assert resolved == ResolvedRun(
        run_dir=run_dir, scenario_name=SCENARIO, db_labels=["baseline_oss"]
    )


async def test_an_owned_row_whose_files_are_gone_is_not_found(
    tmp_path: Path, runs_table: FakeRunsTable
) -> None:
    runs_table.add(group_id=GROUP_A, labels=[])

    with pytest.raises(HTTPException) as raised:
        await resolve(
            request_as(
                runs_dir=tmp_path, pool=CountingPool(), group_id=GROUP_A, is_local_mode=False
            )
        )

    assert raised.value.status_code == 404


async def test_an_owned_row_whose_dir_has_no_event_log_is_not_found(
    tmp_path: Path, runs_table: FakeRunsTable
) -> None:
    """A directory alone is not a run: the claim made before a launch fails leaves one."""
    (tmp_path / SCENARIO / RUN).mkdir(parents=True)
    runs_table.add(group_id=GROUP_A, labels=[])

    with pytest.raises(HTTPException) as raised:
        await resolve(
            request_as(
                runs_dir=tmp_path, pool=CountingPool(), group_id=GROUP_A, is_local_mode=False
            )
        )

    assert raised.value.status_code == 404


async def test_without_a_database_the_files_alone_resolve_the_run(tmp_path: Path) -> None:
    run_dir = write_run(runs_dir=tmp_path)

    resolved = await resolve(
        request_as(runs_dir=tmp_path, pool=None, group_id=uuid4(), is_local_mode=True)
    )

    assert resolved == ResolvedRun(run_dir=run_dir, scenario_name=SCENARIO, db_labels=None)


def test_a_request_the_identity_middleware_never_saw_is_refused(tmp_path: Path) -> None:
    app = SimpleNamespace(state=SimpleNamespace(runs_dir=tmp_path, db_pool=None))
    request = Request(scope={"type": "http", "method": "GET", "headers": [], "app": app})

    with pytest.raises(HTTPException) as raised:
        get_identity(request=request)

    assert raised.value.status_code == 503


# --- registering and deregistering ----------------------------------------------


async def test_a_new_run_is_registered_to_the_active_group_and_its_creator(
    tmp_path: Path, runs_table: FakeRunsTable
) -> None:
    await register_new_run(
        request=request_as(
            runs_dir=tmp_path, pool=CountingPool(), group_id=GROUP_A, is_local_mode=False
        ),
        scenario=SCENARIO,
        run_dir_name=RUN,
        status="running",
        source_run_scenario=SCENARIO,
        source_run_dir_name="1770000050",
        labels=["baseline_oss"],
    )

    assert runs_table.inserted == [
        InsertedRun(
            key=RunKey(group_id=GROUP_A, scenario=SCENARIO, run_dir_name=RUN),
            created_by_user_id="researcher",
            source_run_scenario=SCENARIO,
            source_run_dir_name="1770000050",
            labels=["baseline_oss"],
        )
    ]


async def test_a_run_registered_in_local_mode_names_no_creator(
    tmp_path: Path, runs_table: FakeRunsTable
) -> None:
    """The local identity's user id is synthetic, not a user the database knows."""
    await register_new_run(
        request=request_as(
            runs_dir=tmp_path, pool=CountingPool(), group_id=GROUP_A, is_local_mode=True
        ),
        scenario=SCENARIO,
        run_dir_name=RUN,
        status="running",
        source_run_scenario=None,
        source_run_dir_name=None,
        labels=[],
    )

    assert [inserted.created_by_user_id for inserted in runs_table.inserted] == [None]


async def test_deregistering_removes_only_the_active_groups_row(
    tmp_path: Path, runs_table: FakeRunsTable
) -> None:
    runs_table.add(group_id=GROUP_A, labels=[])
    runs_table.add(group_id=GROUP_B, labels=[])

    await deregister_run(
        request=request_as(
            runs_dir=tmp_path, pool=CountingPool(), group_id=GROUP_B, is_local_mode=False
        ),
        scenario=SCENARIO,
        run_dir_name=RUN,
    )

    assert list(runs_table.rows) == [RunKey(group_id=GROUP_A, scenario=SCENARIO, run_dir_name=RUN)]


async def test_without_a_database_registering_and_deregistering_touch_nothing(
    tmp_path: Path, runs_table: FakeRunsTable
) -> None:
    runs_table.add(group_id=GROUP_A, labels=[])
    request = request_as(runs_dir=tmp_path, pool=None, group_id=GROUP_A, is_local_mode=True)

    await register_new_run(
        request=request,
        scenario=SCENARIO,
        run_dir_name=RUN,
        status="running",
        source_run_scenario=None,
        source_run_dir_name=None,
        labels=[],
    )
    await deregister_run(request=request, scenario=SCENARIO, run_dir_name=RUN)

    assert runs_table.inserted == []
    assert list(runs_table.rows) == [RunKey(group_id=GROUP_A, scenario=SCENARIO, run_dir_name=RUN)]
