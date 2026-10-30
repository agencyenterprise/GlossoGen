"""Checks the committed demo snapshot still has the shape the viewer reads.

``frontend/public/demo/run.json`` is a frozen ``RunDetailResponse``, refreshed
by hand with ``scripts/generate_demo_snapshot.py``. The public ``/demo`` page
fetches it as a static asset and casts it, so nothing on either side validates
it: a field added to the response model renders the snapshot stale, and the
first sign of it is the page throwing in the browser.

``run.zip`` is checked for the same reason. It is written by the same script
and served as the page's download, and a generator that failed partway used to
leave it truncated.
"""

import json
import zipfile
from pathlib import Path

import pytest

from glossogen.server.runs.models import RunDetailResponse

DEMO_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "demo"


@pytest.fixture(name="demo_dir")
def demo_dir_fixture() -> Path:
    """The committed demo assets, or a failure naming what is missing."""
    if not DEMO_DIR.is_dir():
        pytest.fail(f"No demo snapshot directory at {DEMO_DIR}")
    return DEMO_DIR


def test_the_snapshot_validates_against_the_response_model(demo_dir: Path) -> None:
    """A required field added to the model without refreshing this file fails here.

    Reading it back through the model is what the viewer's cast assumes and
    never checks.
    """
    snapshot = json.loads((demo_dir / "run.json").read_text())
    detail = RunDetailResponse.model_validate(snapshot)
    assert detail.messages
    assert detail.agents


def test_the_snapshot_download_is_a_readable_archive(demo_dir: Path) -> None:
    """The zip the page offers must open and hold the run's files."""
    with zipfile.ZipFile(demo_dir / "run.zip") as archive:
        names = archive.namelist()
    assert names
    assert all(name.count("/") >= 1 for name in names)
