"""Setting a run's labels and note over HTTP, and reading them back.

Driven through the app with no database, so ``labels.json`` and ``note.md`` in the
run directory are the only places either is kept.
"""

from pathlib import Path

import orjson
import pytest

from glossogen.run_labels_file import RUN_LABELS_FILENAME, read_run_labels
from tests.fakes.local_app import (
    GROUP_API,
    build_local_app,
    local_client,
    one_round_run_events,
    write_event_log,
)

SCENARIO = "veyru"
RUN = "1770000100"
RUN_API = f"{GROUP_API}/runs/{SCENARIO}/{RUN}"


def _write_run(runs_dir: Path, run_dir_name: str) -> Path:
    return write_event_log(
        runs_dir=runs_dir,
        scenario_name=SCENARIO,
        run_dir_name=run_dir_name,
        events=one_round_run_events(
            scenario_name=SCENARIO, run_dir_name=run_dir_name, finished=True
        ),
        extra_records=[],
    )


async def test_putting_labels_replaces_the_runs_labels(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir, run_dir_name=RUN)
    (run_dir / RUN_LABELS_FILENAME).write_bytes(orjson.dumps(["old", "baseline"]))

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.put(
            f"{RUN_API}/labels", json={"labels": ["baseline", "budget=800"]}
        )
        detail = await client.get(RUN_API)

    assert response.status_code == 200, response.text
    assert response.json() == {"labels": ["baseline", "budget=800"]}
    assert read_run_labels(run_dir=run_dir) == ["baseline", "budget=800"]
    assert detail.json()["labels"] == ["baseline", "budget=800"]


async def test_putting_no_labels_clears_them(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir, run_dir_name=RUN)
    (run_dir / RUN_LABELS_FILENAME).write_bytes(orjson.dumps(["baseline"]))

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.put(f"{RUN_API}/labels", json={"labels": []})
        detail = await client.get(RUN_API)

    assert response.status_code == 200, response.text
    assert detail.json()["labels"] == []


async def test_the_group_label_list_shows_a_label_put_after_it_was_read(tmp_path: Path) -> None:
    """The group's label union is cached; putting labels must drop the cached copy."""
    runs_dir = tmp_path / "runs"
    first_dir = _write_run(runs_dir=runs_dir, run_dir_name=RUN)
    (first_dir / RUN_LABELS_FILENAME).write_bytes(orjson.dumps(["baseline"]))
    _write_run(runs_dir=runs_dir, run_dir_name="1770000200")

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        before = await client.get(f"{GROUP_API}/labels")
        await client.put(
            f"{GROUP_API}/runs/{SCENARIO}/1770000200/labels", json={"labels": ["budget=800"]}
        )
        after = await client.get(f"{GROUP_API}/labels")

    assert before.json()["labels"] == ["baseline"]
    assert after.json()["labels"] == ["baseline", "budget=800"]


async def test_labels_that_are_not_strings_are_refused_and_the_file_is_kept(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir, run_dir_name=RUN)
    (run_dir / RUN_LABELS_FILENAME).write_bytes(orjson.dumps(["baseline"]))

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.put(f"{RUN_API}/labels", json={"labels": ["baseline", 800]})

    assert response.status_code == 422
    assert read_run_labels(run_dir=run_dir) == ["baseline"]


async def test_a_run_with_no_note_reads_as_null(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _write_run(runs_dir=runs_dir, run_dir_name=RUN)

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.get(f"{RUN_API}/note")

    assert response.status_code == 200
    assert response.json() == {"content": None}


async def test_a_note_put_twice_reads_back_as_the_second(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _write_run(runs_dir=runs_dir, run_dir_name=RUN)
    second = "Agents settled on «kre» for red by round 4.\n\n- recheck the swap"

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        await client.put(f"{RUN_API}/note", json={"content": "a longer first draft of the note"})
        response = await client.put(f"{RUN_API}/note", json={"content": second})
        read_back = await client.get(f"{RUN_API}/note")

    assert response.status_code == 200, response.text
    assert response.json() == {"content": second}
    assert read_back.json() == {"content": second}


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        pytest.param("PUT", "labels", {"labels": ["baseline"]}, id="put labels"),
        pytest.param("PUT", "note", {"content": "text"}, id="put note"),
        pytest.param("GET", "note", None, id="get note"),
    ],
)
async def test_an_unknown_run_answers_404_and_creates_nothing(
    tmp_path: Path, method: str, path: str, body: dict[str, object] | None
) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.request(method=method, url=f"{RUN_API}/{path}", json=body)

    assert response.status_code == 404
    assert list(runs_dir.iterdir()) == []
