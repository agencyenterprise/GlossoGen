"""Availability probes and loaders for the optional ``metrics-ml`` dependency set.

``torch``, ``minicons``, and ``datasets`` are multi-gigabyte installs needed by
exactly three metrics: ``perplexity`` and the two English n-gram surprisal
metrics. They ship in the optional ``metrics-ml`` extra so the simulation server
image does not carry an ML stack it never executes.

Every metric that needs them stays importable — and therefore registered —
without the extra installed. This module owns the conditional loading so those
metrics report a clean skip, matching the not-applicable convention used
elsewhere in the metric suite (return no ``Measurement`` rather than a zero
sentinel).

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


def missing_extra_message(metric_name: str, reason: str) -> str:
    """Build a skip message naming the metric, the reason, and the install command."""
    return (
        f"{metric_name}: skipping — {reason}. Install the optional dependency "
        f"set with `uv sync --extra {METRICS_ML_EXTRA}` to enable this metric."
    )


def load_incremental_lm_scorer() -> Any:
    """Return ``minicons.scorer.IncrementalLMScorer``.

    Call only when ``is_perplexity_backend_available()`` is True.
    """
    scorer_module = importlib.import_module("minicons.scorer")
    return scorer_module.IncrementalLMScorer


def resolve_torch_device() -> str:
    """Return ``"cuda"`` when a CUDA device is visible to torch, else ``"cpu"``.

    Call only when ``is_perplexity_backend_available()`` is True.
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
