"""Carrying the local label glossary to a remote with ``sync-metadata-to-prod``.

The plan is local-wins for entries both sides have and additive for the rest:
a description only the remote has is not deleted, because it may have been
recorded on prod directly. The HTTP tests drive ``sync_glossary`` against an
httpx ``MockTransport`` standing in for the remote's glossary endpoints.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from glossogen.db.local_tenant import LOCAL_GROUP_ID
from glossogen.label_descriptions.filesystem_label_description_store import (
    FilesystemLabelDescriptionStore,
)
from glossogen.label_descriptions.label_description_models import LabelDescription
from glossogen.oauth_client import Credentials
from glossogen.prod_metadata_sync import MetadataSyncTally, plan_glossary_sync, sync_glossary


def test_the_plan_carries_entries_the_remote_is_missing_or_records_differently() -> None:
    local = [
        LabelDescription(label="baseline_oss", description="Open-weight baseline cohort"),
        LabelDescription(label="budget=800", description="800-second round time budget"),
        LabelDescription(label="cross_team", description="Imported-observer runs"),
    ]
    remote = {
        "baseline_oss": "Open-weight baseline cohort",
        "budget=800": "First guess",
    }

    pending = plan_glossary_sync(local=local, remote=remote)

    assert [entry.label for entry in pending] == ["budget=800", "cross_team"]


def test_the_plan_leaves_remote_only_descriptions_alone() -> None:
    remote = {"prod_only": "Recorded on prod directly"}

    assert plan_glossary_sync(local=[], remote=remote) == []


def test_an_identical_glossary_plans_nothing() -> None:
    local = [LabelDescription(label="channel_noise", description="The noise sweep")]
    remote = {"channel_noise": "The noise sweep"}

    assert plan_glossary_sync(local=local, remote=remote) == []


def _credentials() -> Credentials:
    return Credentials(
        issuer_url="https://prod.example",
        group_slug="ae-group",
        client_id="client",
        client_secret=None,
        access_token="token",
        refresh_token=None,
        expires_at=datetime(2100, 1, 1, tzinfo=UTC),
    )


class _FakeGlossaryRemote:
    """Answers GET /labels/descriptions and records the PUT bodies it receives."""

    def __init__(self, descriptions: dict[str, str]) -> None:
        self._descriptions = descriptions
        self.put_bodies: list[dict[str, str]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/g/ae-group/labels/descriptions"
        assert request.headers["Authorization"] == "Bearer token"
        if request.method == "GET":
            payload = {
                "descriptions": [
                    {"label": label, "description": description}
                    for label, description in self._descriptions.items()
                ]
            }
            return httpx.Response(status_code=200, json=payload)
        assert request.method == "PUT"
        body = json.loads(request.content)
        self.put_bodies.append(body)
        return httpx.Response(status_code=200, json=body)


async def _write_local_glossary(*, runs_dir: Path, entries: list[LabelDescription]) -> None:
    store = FilesystemLabelDescriptionStore(runs_dir=runs_dir)
    for entry in entries:
        await store.set_description(group_id=LOCAL_GROUP_ID, entry=entry)


async def test_drifted_descriptions_are_put_and_tallied(tmp_path: Path) -> None:
    await _write_local_glossary(
        runs_dir=tmp_path,
        entries=[
            LabelDescription(label="baseline_oss", description="Open-weight baseline cohort"),
            LabelDescription(label="budget=800", description="800-second round time budget"),
        ],
    )
    remote = _FakeGlossaryRemote(descriptions={"baseline_oss": "Open-weight baseline cohort"})
    tally = MetadataSyncTally()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler=remote.handle)) as client:
        await sync_glossary(
            client=client,
            credentials=_credentials(),
            runs_dir=tmp_path,
            dry_run=False,
            tally=tally,
        )

    assert remote.put_bodies == [
        {"label": "budget=800", "description": "800-second round time budget"}
    ]
    assert tally.synced_descriptions == ["budget=800"]
    assert tally.failed == []


async def test_a_dry_run_puts_nothing(tmp_path: Path) -> None:
    await _write_local_glossary(
        runs_dir=tmp_path,
        entries=[LabelDescription(label="cross_team", description="Imported-observer runs")],
    )
    remote = _FakeGlossaryRemote(descriptions={})
    tally = MetadataSyncTally()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler=remote.handle)) as client:
        await sync_glossary(
            client=client,
            credentials=_credentials(),
            runs_dir=tmp_path,
            dry_run=True,
            tally=tally,
        )

    assert remote.put_bodies == []
    assert tally.synced_descriptions == []


async def test_a_failed_put_lands_in_the_tally_and_does_not_stop_the_rest(
    tmp_path: Path,
) -> None:
    await _write_local_glossary(
        runs_dir=tmp_path,
        entries=[
            LabelDescription(label="refused", description="The remote rejects this one"),
            LabelDescription(label="works", description="This one lands"),
        ],
    )

    class _FailingRemote(_FakeGlossaryRemote):
        def handle(self, request: httpx.Request) -> httpx.Response:
            if request.method == "PUT" and json.loads(request.content)["label"] == "refused":
                return httpx.Response(status_code=422, json={"detail": "no"})
            return super().handle(request)

    remote = _FailingRemote(descriptions={})
    tally = MetadataSyncTally()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler=remote.handle)) as client:
        await sync_glossary(
            client=client,
            credentials=_credentials(),
            runs_dir=tmp_path,
            dry_run=False,
            tally=tally,
        )

    assert tally.synced_descriptions == ["works"]
    assert [subject for subject, _ in tally.failed] == ["label-description refused"]
