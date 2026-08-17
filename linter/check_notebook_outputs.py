#!/usr/bin/env python3
"""Custom linting script to keep executed output out of committed notebooks.

A notebook stores its output inside the document, so opening one, running it and
saving writes hundreds of lines into the file. The diff of the next real change is
then buried under regenerated output, and reviewing it means reading past base64
image payloads to find the one edited line.

Nothing about that is visible to whoever does it: the notebook looks the same, and
`git add` takes the whole file. So it is checked here rather than left to a
convention, and the fix it prints is the command that strips them.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple, cast

NOTEBOOK_SUFFIX = ".ipynb"


class Finding(NamedTuple):
    """One notebook carrying output, and how much."""

    path: Path
    cells_with_output: int
    outputs: int
    executed_cells: int


def main() -> None:
    """Check every notebook under the target directory and report what carries output."""
    parser = argparse.ArgumentParser(description="Keep output out of committed notebooks")
    parser.add_argument("--target-dir", type=str, required=True, help="Directory to check")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Directory name to skip; repeatable",
    )
    parser.add_argument(
        "--strip",
        action="store_true",
        help="Remove the output rather than reporting it, and exit zero",
    )
    args = parser.parse_args()

    excluded = set(args.exclude)
    findings: list[Finding] = []
    checked = 0
    for path in sorted(Path(args.target_dir).resolve().rglob(f"*{NOTEBOOK_SUFFIX}")):
        if excluded & set(path.parts):
            continue
        checked += 1
        finding = inspect(path=path)
        if finding is not None:
            findings.append(finding)

    if not findings:
        print(f"No committed notebook output found ({checked} notebook(s) checked)")
        sys.exit(0)

    if args.strip:
        for finding in findings:
            strip(path=finding.path)
            print(f"Stripped {finding.outputs} output(s) from {finding.path}")
        sys.exit(0)

    for finding in findings:
        print(f"\n{finding.path}:")
        print(
            f"  {finding.outputs} output(s) across {finding.cells_with_output} cell(s), "
            f"and {finding.executed_cells} cell(s) carrying an execution count"
        )
    print(f"\n Found output in {len(findings)} notebook(s). Strip it with:")
    print("   VIRTUAL_ENV= uv run --no-sync python linter/check_notebook_outputs.py \\")
    print(f"     --target-dir {args.target_dir} --strip")
    sys.exit(1)


def inspect(path: Path) -> Finding | None:
    """Return what output this notebook carries, or None when it carries none.

    A notebook that does not parse is left to the tools that run it; this one is
    only asked whether output was committed.
    """
    cells = cells_of(path=path)
    if cells is None:
        return None

    with_output = [cell for cell in cells if cell.get("outputs")]
    executed = [cell for cell in cells if cell.get("execution_count") is not None]
    if not with_output and not executed:
        return None
    return Finding(
        path=path,
        cells_with_output=len(with_output),
        outputs=sum(len(cell["outputs"]) for cell in with_output),
        executed_cells=len(executed),
    )


def cells_of(path: Path) -> list[dict[str, Any]] | None:
    """Return a notebook's cells, or None when the file is not a readable notebook."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(document, dict):
        return None
    found = cast(dict[str, Any], document).get("cells")
    if not isinstance(found, list):
        return None
    cells = cast(list[object], found)
    return [cast(dict[str, Any], cell) for cell in cells if isinstance(cell, dict)]


def strip(path: Path) -> None:
    """Clear every cell's output and execution count, in place.

    Written back with the same shape a freshly authored notebook has: an empty
    output list and no execution count, so a stripped file and a new one diff
    against each other cleanly.
    """
    document = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    for cell in cast(list[dict[str, Any]], document["cells"]):
        if cell.get("cell_type") != "code":
            continue
        cell["outputs"] = []
        cell["execution_count"] = None
    path.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
