"""Check that a wheel contains exactly the package files selected from src/."""

import argparse
import zipfile
from pathlib import Path

PACKAGE_DATA_SUFFIXES = {".jinja", ".json", ".tsv"}


def _expected_files(source_root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(source_root).as_posix(): path.read_bytes()
        for path in source_root.rglob("*")
        if path.is_file()
        and (
            path.suffix == ".py" or path.suffix in PACKAGE_DATA_SUFFIXES or path.name == "py.typed"
        )
    }


def _packaged_files(wheel_path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(wheel_path) as wheel:
        return {
            name: wheel.read(name) for name in wheel.namelist() if name.startswith("glossogen/")
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()

    source_root = Path(__file__).resolve().parents[1] / "src" / "glossogen"
    expected = _expected_files(source_root)
    expected = {f"glossogen/{name}": content for name, content in expected.items()}
    packaged = _packaged_files(args.wheel)
    missing = sorted(expected.keys() - packaged.keys())
    unexpected = sorted(packaged.keys() - expected.keys())
    changed = sorted(
        name for name in expected.keys() & packaged.keys() if expected[name] != packaged[name]
    )
    if missing or unexpected or changed:
        details = []
        if missing:
            details.append("missing:\n  " + "\n  ".join(missing))
        if unexpected:
            details.append("unexpected:\n  " + "\n  ".join(unexpected))
        if changed:
            details.append("content differs:\n  " + "\n  ".join(changed))
        raise SystemExit("Wheel content differs from src/:\n" + "\n".join(details))

    print(f"Wheel contains the {len(expected)} expected package files.")


if __name__ == "__main__":
    main()
