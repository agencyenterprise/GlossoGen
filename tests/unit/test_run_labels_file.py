"""What a run's ``labels.json`` reads as, for a well-formed file and for each broken shape.

``load_run_labels`` separates "no readable labels" (``None``) from an empty list,
which is what lets ``push-to-prod`` skip a run with no labels file while the server
shows the same run with no labels.
"""

from pathlib import Path

import pytest

from glossogen.run_storage.run_labels_file import load_run_labels, read_run_labels


def test_a_list_of_strings_reads_as_those_labels(tmp_path: Path) -> None:
    (tmp_path / "labels.json").write_text('["baseline", "budget=800"]')

    assert load_run_labels(run_dir=tmp_path) == ["baseline", "budget=800"]
    assert read_run_labels(run_dir=tmp_path) == ["baseline", "budget=800"]


def test_an_empty_list_is_an_empty_list_rather_than_missing(tmp_path: Path) -> None:
    (tmp_path / "labels.json").write_text("[]")

    assert load_run_labels(run_dir=tmp_path) == []


def test_a_missing_file_reads_as_no_labels(tmp_path: Path) -> None:
    assert load_run_labels(run_dir=tmp_path) is None
    assert read_run_labels(run_dir=tmp_path) == []


@pytest.mark.parametrize(
    "content",
    [
        pytest.param('["baseline"', id="truncated JSON"),
        pytest.param('{"labels": ["baseline"]}', id="an object"),
        pytest.param('"baseline"', id="a bare string"),
        pytest.param('["baseline", 3]', id="a non-string label"),
        pytest.param(b"\xff\xfe", id="bytes that are not UTF-8"),
    ],
)
def test_a_file_that_is_not_a_list_of_strings_reads_as_no_labels(
    tmp_path: Path, content: str | bytes
) -> None:
    labels_path = tmp_path / "labels.json"
    if isinstance(content, bytes):
        labels_path.write_bytes(content)
    else:
        labels_path.write_text(content)

    assert load_run_labels(run_dir=tmp_path) is None
    assert read_run_labels(run_dir=tmp_path) == []
