"""Every registered metric has a test file, and every test file names a metric.

The metric registry is what `glossogen evaluate --metrics` resolves against, so
a metric can be added, shipped and run against real simulations without anyone
noticing it was never scored in a test. This is the check that makes adding one
without a test a red build rather than a thing someone spots later.

Both directions matter. A file for a metric that no longer exists is a test
still passing against code nobody calls.
"""

from pathlib import Path

from glossogen.evaluation.metric_core.metric_registry import GENERIC_METRIC_REGISTRY

METRICS_TEST_DIR = Path(__file__).resolve().parents[1] / "metrics"

# Files under tests/metrics that cover the shared machinery rather than one
# metric. Anything else there is expected to be named after a metric.
NON_METRIC_FILES = frozenset({"shared_run", "report_writing"})


def metric_test_names() -> set[str]:
    """Return the metric name each test file claims to cover, from its filename."""
    return {path.stem.removeprefix("test_") for path in METRICS_TEST_DIR.glob("test_*.py")}


def test_every_registered_metric_has_a_test_file() -> None:
    """A new metric needs `tests/metrics/test_<name>.py` before it can land."""
    missing = sorted(set(GENERIC_METRIC_REGISTRY) - metric_test_names())
    assert not missing, (
        f"registered but never tested: {missing}. Add tests/metrics/test_<name>.py; "
        f"the shared run and harness are already there."
    )


def test_every_metric_test_file_names_a_real_metric() -> None:
    """A file for a metric that was renamed or deleted tests nothing."""
    unknown = sorted(metric_test_names() - set(GENERIC_METRIC_REGISTRY) - NON_METRIC_FILES)
    assert not unknown, (
        f"test files that match no registered metric: {unknown}. Rename the file to "
        f"the metric it covers, or add it to NON_METRIC_FILES if it covers shared machinery."
    )
