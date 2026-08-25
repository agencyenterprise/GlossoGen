"""Recording, listing, replacing, and deleting label descriptions.

The suite runs with no ``DATABASE_URL``, so these drive the filesystem store, which
is what a single-tenant checkout uses. Both stores implement one contract and the
router only ever calls through it, so what is pinned here is that contract: group
scoping, one description per label, and a description that survives being written
and read back.

The Postgres store's own SQL is exercised by the migration and by running the server
against a database; there is no live database in this suite to point it at.
"""

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from glossogen.label_descriptions.filesystem_label_description_store import (
    FilesystemLabelDescriptionStore,
)
from glossogen.label_descriptions.label_description_models import LabelDescription


async def test_a_recorded_description_reads_back_sorted_by_label(tmp_path: Path) -> None:
    store = FilesystemLabelDescriptionStore(runs_dir=tmp_path)
    group_id = uuid4()

    await store.set_description(
        group_id=group_id,
        entry=LabelDescription(label="channel_noise", description="The 2026-06-19 noise sweep"),
    )
    await store.set_description(
        group_id=group_id,
        entry=LabelDescription(label="baseline_oss", description="Open-weight baseline cohort"),
    )

    listed = await store.list_descriptions(group_id=group_id)
    assert [entry.label for entry in listed] == ["baseline_oss", "channel_noise"]
    assert listed[0].description == "Open-weight baseline cohort"


async def test_describing_a_label_again_replaces_its_description(tmp_path: Path) -> None:
    store = FilesystemLabelDescriptionStore(runs_dir=tmp_path)
    group_id = uuid4()
    await store.set_description(
        group_id=group_id,
        entry=LabelDescription(label="budget=800", description="First guess"),
    )

    await store.set_description(
        group_id=group_id,
        entry=LabelDescription(label="budget=800", description="800-second round time budget"),
    )

    listed = await store.list_descriptions(group_id=group_id)
    assert listed == [
        LabelDescription(label="budget=800", description="800-second round time budget")
    ]


async def test_a_label_with_a_path_separator_is_stored_like_any_other(tmp_path: Path) -> None:
    store = FilesystemLabelDescriptionStore(runs_dir=tmp_path)
    group_id = uuid4()
    label = "src=veyru/1777638061"

    await store.set_description(
        group_id=group_id,
        entry=LabelDescription(label=label, description="Derived from the noise-sweep source"),
    )

    listed = await store.list_descriptions(group_id=group_id)
    assert [entry.label for entry in listed] == [label]


async def test_one_groups_glossary_is_invisible_to_another(tmp_path: Path) -> None:
    store = FilesystemLabelDescriptionStore(runs_dir=tmp_path)
    owner = uuid4()
    await store.set_description(
        group_id=owner,
        entry=LabelDescription(label="cross_team", description="Imported-observer runs"),
    )

    assert await store.list_descriptions(group_id=uuid4()) == []


async def test_deleting_returns_whether_a_description_was_there(tmp_path: Path) -> None:
    store = FilesystemLabelDescriptionStore(runs_dir=tmp_path)
    group_id = uuid4()
    await store.set_description(
        group_id=group_id,
        entry=LabelDescription(label="cross_team", description="Imported-observer runs"),
    )

    assert await store.delete_description(group_id=group_id, label="cross_team") is True
    assert await store.delete_description(group_id=group_id, label="cross_team") is False
    assert await store.list_descriptions(group_id=group_id) == []


async def test_a_group_that_never_recorded_anything_lists_empty(tmp_path: Path) -> None:
    store = FilesystemLabelDescriptionStore(runs_dir=tmp_path)

    assert await store.list_descriptions(group_id=uuid4()) == []


def test_an_empty_description_is_refused_at_the_model() -> None:
    with pytest.raises(ValidationError):
        LabelDescription(label="baseline_oss", description="")


def test_an_empty_label_is_refused_at_the_model() -> None:
    with pytest.raises(ValidationError):
        LabelDescription(label="", description="Something")
