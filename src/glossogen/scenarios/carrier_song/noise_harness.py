"""Runs inside the Python sandbox: loads a player's executor and prints the noise it returns.

The sandbox's working directory holds ``noise.py``, the player's executor, and
``song.json``, the round's song. The executor is run as a module of its own, its
``noise`` function is called with the song, and the return value is printed as
JSON on one line after ``RESULT_MARKER``. Anything the executor printed comes
before that line. The sandbox has the standard library only, so this module
imports nothing outside it.
"""

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

RESULT_MARKER = "@@noise_result@@ "


def main() -> None:
    """Run ``noise.py`` on ``song.json`` and print the result after the marker."""
    song = json.loads(Path("song.json").read_text(encoding="utf-8"))
    namespace: dict[str, object] = {"__name__": "noise"}
    exec(compile(Path("noise.py").read_text(encoding="utf-8"), "noise.py", "exec"), namespace)
    function = namespace.get("noise")
    if not callable(function):
        print("noise.py defines no function named noise", file=sys.stderr)
        sys.exit(1)
    result = cast(Callable[[list[int]], object], function)(list(song))
    if not isinstance(result, list):
        print(f"noise(song) must return a list, not {type(result).__name__}", file=sys.stderr)
        sys.exit(1)
    sys.stdout.flush()
    print(RESULT_MARKER + json.dumps(result))


if __name__ == "__main__":
    main()
