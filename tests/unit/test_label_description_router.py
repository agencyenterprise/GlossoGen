"""The label-description endpoints: what they refuse, and who can see what.

The store is tested directly elsewhere. What the router adds is group scoping and the
one refusal a client has to recognise: deleting a description that is not there is a
404. Driven against the filesystem store, which is what a no-database deployment runs
and what this suite has.
"""

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, Request

from glossogen.label_descriptions.label_description_models import LabelDescription
from glossogen.server.identity.identity_model import Identity
from glossogen.server.runs.label_description_router import (
    delete_label_description,
    list_label_descriptions,
    set_label_description,
)


def request_for(runs_dir: Path, group_id: UUID) -> Request:
    """A request carrying the runs directory and one group's identity."""
    app = SimpleNamespace(state=SimpleNamespace(db_pool=None, runs_dir=runs_dir))
    request = Request(scope={"type": "http", "method": "PUT", "headers": [], "app": app})
    request.state.identity = Identity(
        user_id="local-user", active_group_id=group_id, is_local_mode=True
    )
    return request


async def test_a_recorded_description_comes_back_on_the_group_listing(tmp_path: Path) -> None:
    request = request_for(runs_dir=tmp_path, group_id=uuid4())
    entry = LabelDescription(label="baseline_oss", description="Open-weight baseline cohort")

    returned = await set_label_description(body=entry, request=request)
    listed = await list_label_descriptions(request=request)

    assert returned == entry
    assert listed.descriptions == [entry]


async def test_describing_a_label_again_replaces_rather_than_duplicates(tmp_path: Path) -> None:
    request = request_for(runs_dir=tmp_path, group_id=uuid4())
    await set_label_description(
        body=LabelDescription(label="budget=800", description="First guess"),
        request=request,
    )

    await set_label_description(
        body=LabelDescription(label="budget=800", description="800-second round time budget"),
        request=request,
    )

    listed = await list_label_descriptions(request=request)
    assert listed.descriptions == [
        LabelDescription(label="budget=800", description="800-second round time budget")
    ]


async def test_another_groups_descriptions_read_as_absent(tmp_path: Path) -> None:
    owner = request_for(runs_dir=tmp_path, group_id=uuid4())
    stranger = request_for(runs_dir=tmp_path, group_id=uuid4())
    await set_label_description(
        body=LabelDescription(label="cross_team", description="Imported-observer runs"),
        request=owner,
    )

    listed = await list_label_descriptions(request=stranger)
    assert listed.descriptions == []


async def test_another_group_cannot_delete_a_description_either(tmp_path: Path) -> None:
    owner = request_for(runs_dir=tmp_path, group_id=uuid4())
    stranger = request_for(runs_dir=tmp_path, group_id=uuid4())
    await set_label_description(
        body=LabelDescription(label="cross_team", description="Imported-observer runs"),
        request=owner,
    )

    with pytest.raises(HTTPException) as refusal:
        await delete_label_description(label="cross_team", request=stranger)

    assert refusal.value.status_code == 404
    listed = await list_label_descriptions(request=owner)
    assert [entry.label for entry in listed.descriptions] == ["cross_team"]


async def test_deleting_twice_is_a_404_the_second_time(tmp_path: Path) -> None:
    request = request_for(runs_dir=tmp_path, group_id=uuid4())
    await set_label_description(
        body=LabelDescription(label="cross_team", description="Imported-observer runs"),
        request=request,
    )

    response = await delete_label_description(label="cross_team", request=request)
    assert response.status_code == 204

    with pytest.raises(HTTPException) as refusal:
        await delete_label_description(label="cross_team", request=request)
    assert refusal.value.status_code == 404
