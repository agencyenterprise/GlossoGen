"""Which files inside a run directory an archive carries.

Two exclusion sets, because they are excluded for different reasons and only one
of them is negotiable. Logs are dropped by default for size: a run's
`_debug.jsonl` is routinely larger than the event log everything is read from.
An export can ask for them back.

Live-state files are dropped always. `stream.json` tells the server a simulation
is running and streaming on a port; `eval_in_progress.json` tells it an
evaluation is mid-flight. Either one inside an imported archive describes work
that is not happening, and the run reads as busy on the machine that imports it.
"""

from pathlib import Path

ALWAYS_EXCLUDED_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        "stream.json",
        "eval_in_progress.json",
        # A derived cache the reader trusts on sight: it carries no key saying which
        # run it was built from, so an imported run inherits another run's summary.
        "run_summary_cache.json",
    }
)

LOG_EXCLUDED_NAMES: frozenset[str] = frozenset({"eval_stdout.log"})

LOG_EXCLUDED_SUFFIXES: tuple[str, ...] = (
    "_debug.jsonl",
    "_stdout.log",
    "_start.log",
)


def should_include_in_archive(path: Path, run_dir: Path, include_logs: bool) -> bool:
    """Return True if ``path`` belongs in an archive of ``run_dir``.

    ``include_logs=False`` drops the debug and stdout logs. Live-state files are
    dropped either way.
    """
    relative = path.relative_to(run_dir)
    for part in relative.parts:
        if part in ALWAYS_EXCLUDED_NAMES:
            return False

    if include_logs:
        return True

    name = relative.name
    if name in LOG_EXCLUDED_NAMES:
        return False
    for suffix in LOG_EXCLUDED_SUFFIXES:
        if name.endswith(suffix):
            return False
    return True
