"""The type of a manifest field that names a file inside the manifest's own run directory.

Readers join such a field onto the run directory and open the result. A manifest can
arrive in an uploaded bundle, so the field is refused unless it is a bare file name:
a path with a separator, an absolute path or ``..`` would let the uploader choose a
file in another run, including another group's on a shared runs directory.
"""

from typing import Annotated

from pydantic import AfterValidator


def _require_bare_file_name(value: str) -> str:
    """Return ``value`` if it names a file directly inside a directory, else raise."""
    if value in ("", ".", "..") or "/" in value or "\\" in value or "\0" in value:
        raise ValueError(f"must be a file name inside the run directory, got {value!r}")
    return value


RunDirFileName = Annotated[str, AfterValidator(_require_bare_file_name)]
"""A file name with no directory part, read relative to the run directory."""
