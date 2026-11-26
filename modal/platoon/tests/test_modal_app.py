"""The code that runs in the Modal image parses as the image's Python, 3.12; this project and the
repository's formatter target 3.14."""

import ast

from episodes import PROJECT_ROOT


def test_the_modules_that_run_on_modal_parse_as_python_3_12() -> None:
    paths = [
        PROJECT_ROOT / "platoon_app.py",
        *sorted((PROJECT_ROOT / "tinker_service").glob("*.py")),
    ]
    for path in paths:
        ast.parse(path.read_text(), filename=str(path), feature_version=(3, 12))
