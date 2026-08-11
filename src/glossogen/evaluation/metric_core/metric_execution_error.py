"""Error raised when one or more requested metrics could not be computed.

Evaluation runs every requested metric before reporting failure, so a single
broken metric does not discard the results of the others. The report is still
written with whatever succeeded. The failure is then raised so the process exits
non-zero.

The alternative, logging a warning and exiting zero, makes a broken environment
or a crashing metric indistinguishable from a clean run. A caller scripting over
``glossogen evaluate`` has no way to notice, and a partial report reads as a
complete one.
"""


class MetricExecutionError(RuntimeError):
    """One or more requested metrics raised while computing.

    ``failed_metric_names`` lists the metrics that failed, in request order.
    Individual causes are logged with full stack traces as they occur.
    """

    def __init__(self, failed_metric_names: list[str], report_path: str) -> None:
        self.failed_metric_names = failed_metric_names
        self.report_path = report_path
        joined = ", ".join(failed_metric_names)
        super().__init__(
            f"{len(failed_metric_names)} metric(s) failed: {joined}. "
            f"Results from the metrics that succeeded were still written to "
            f"{report_path}. See the logged tracebacks above for each cause."
        )
