"""Raw exports stay within the selected run directory."""

import io
import zipfile
from pathlib import Path, PurePosixPath

from glossogen.run_export.runs_zip_archive import add_run_to_zip


def test_raw_archive_does_not_follow_file_symlinks(tmp_path: Path) -> None:
    """A run-local symlink must not copy its external target into the zip."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "owned.txt").write_bytes(b"owned")
    external = tmp_path / "external-secret.txt"
    external.write_bytes(b"not part of the run")
    (run_dir / "linked-secret.txt").symlink_to(external)
    destination = io.BytesIO()

    with zipfile.ZipFile(destination, mode="w") as archive:
        tally = add_run_to_zip(
            archive=archive,
            run_dir=run_dir,
            arc_root=PurePosixPath("run"),
            scenario_name="scenario",
            include_logs=True,
            include_atif=False,
        )

    with zipfile.ZipFile(io.BytesIO(destination.getvalue())) as archive:
        assert archive.namelist() == ["run/owned.txt"]
        assert archive.read("run/owned.txt") == b"owned"
    assert tally.file_count == 1
    assert tally.byte_count == len(b"owned")
