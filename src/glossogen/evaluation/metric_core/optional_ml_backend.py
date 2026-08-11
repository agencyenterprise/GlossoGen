"""Availability probes and loaders for the optional ``metrics-ml`` dependency set.

``torch``, ``minicons``, and ``datasets`` are multi-gigabyte installs needed by
the ``perplexity`` and English n-gram surprisal
metrics. They ship in the optional ``metrics-ml`` extra so the simulation server
image does not carry an ML stack it never executes.

Every metric that needs them stays importable, and therefore registered,
without the extra installed, so the absence surfaces as an explicit failure at
compute time rather than an ``ImportError`` at registry-import time.

**A missing extra is an error, not a skip.** Asking for ``perplexity`` and
receiving no measurement would be indistinguishable from a run with nothing to
measure, which is how a broken environment gets mistaken for a valid result.
The metrics therefore raise ``MetricsMlExtraMissing``. That is deliberately
different from the not-applicable convention (returning no ``Measurement``),
which is reserved for cases where the metric genuinely does not apply to the
run, such as a scenario with no primary channel.

The two metric families have different requirements, so the probes are
separate:

- ``perplexity`` needs ``torch`` + ``minicons`` on every invocation.
- The n-gram metrics need ``datasets`` **only to train a model from wikitext**.
  Both cache the trained model under ``~/.cache/glossogen/``, so a warm cache
  runs them with no ML dependency at all.

Loading goes through ``importlib.import_module`` rather than a module-scope
import so absence surfaces as a skip at compute time instead of an
``ImportError`` at registry-import time.
"""

import importlib
import importlib.util
from typing import Any

METRICS_ML_EXTRA = "metrics-ml"

_PERPLEXITY_MODULES = ("torch", "minicons")
_DATASET_MODULES = ("datasets",)


class MetricsMlExtraMissing(RuntimeError):
    """Raised when work genuinely requires the optional ML extra and it is absent.

    Callers that can proceed without it (for example an n-gram metric reading a
    cached model) should never see this.
    """


def _all_importable(module_names: tuple[str, ...]) -> bool:
    """Report whether every named top-level module can be located."""
    for module_name in module_names:
        try:
            if importlib.util.find_spec(module_name) is None:
                return False
        except (ImportError, ValueError):
            return False
    return True


def is_perplexity_backend_available() -> bool:
    """Report whether ``torch`` and ``minicons`` are importable."""
    return _all_importable(module_names=_PERPLEXITY_MODULES)


def is_dataset_backend_available() -> bool:
    """Report whether ``datasets`` is importable."""
    return _all_importable(module_names=_DATASET_MODULES)


def require_perplexity_backend(metric_name: str) -> None:
    """Raise ``MetricsMlExtraMissing`` unless ``torch`` and ``minicons`` are importable.

    Called at the top of a metric's ``compute`` so an unrunnable metric fails
    loudly instead of returning an empty result that reads as "nothing to
    measure".
    """
    if is_perplexity_backend_available():
        return
    raise MetricsMlExtraMissing(
        f"{metric_name} requires `torch` and `minicons`, which are not "
        f"installed. Install them with `uv sync --extra {METRICS_ML_EXTRA}` "
        f"(or `make install-metrics`), or drop {metric_name} from --metrics."
    )


def load_incremental_lm_scorer() -> Any:
    """Return ``minicons.scorer.IncrementalLMScorer``.

    Call only after ``require_perplexity_backend`` has passed.
    """
    scorer_module = importlib.import_module("minicons.scorer")
    return scorer_module.IncrementalLMScorer


def resolve_torch_device() -> str:
    """Return ``"cuda"`` when a CUDA device is visible to torch, else ``"cpu"``.

    Call only after ``require_perplexity_backend`` has passed.
    """
    torch_module = importlib.import_module("torch")
    if torch_module.cuda.is_available():
        return "cuda"
    return "cpu"


def load_hf_dataset_loader() -> Any:
    """Return ``datasets.load_dataset``.

    Raises ``MetricsMlExtraMissing`` when ``datasets`` is not installed, so a
    cold-cache n-gram build fails with an actionable message rather than an
    ``ImportError`` from an unexpected place.
    """
    if not is_dataset_backend_available():
        raise MetricsMlExtraMissing(
            f"Training an n-gram model from wikitext requires the "
            f"'{METRICS_ML_EXTRA}' extra (provides `datasets`). Install it with "
            f"`uv sync --extra {METRICS_ML_EXTRA}`, or supply a pre-built model "
            f"cache under ~/.cache/glossogen/."
        )
    datasets_module = importlib.import_module("datasets")
    return datasets_module.load_dataset
