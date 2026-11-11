"""Registry mapping metric names to their classes.

Generic metrics are scenario-agnostic and available to all scenarios. The
registry maps each metric's ``name`` to its zero-argument class so the
caller can instantiate with ``cls()`` and then pass per-invocation
``MetricRunOptions`` into ``cls.compute(...)``.

``GENERIC_METRIC_REGISTRY`` holds the generic metrics shipped here, the ones
every scenario offers. A metric that applies to one scenario is not listed here:
that scenario returns it from ``scenario_metrics()``, so this module names no
scenario. :func:`available_metrics` merges the generic metrics, the scenario's
own, and the ones other installed distributions declare; call that rather than
reading the dict, unless you specifically mean the generic set.
"""

import logging
from importlib.metadata import EntryPoint

from glossogen.evaluation.metric_core.metric_entry_points import external_metric_entry_points
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metrics.communication.communication_feature_presence_metric import (
    CommunicationFeaturePresenceMetric,
)
from glossogen.evaluation.metrics.communication.communication_open_coding_metric import (
    CommunicationOpenCodingMetric,
)
from glossogen.evaluation.metrics.content_filter_refusal_metric import ContentFilterRefusalMetric
from glossogen.evaluation.metrics.dialog_retransmission_metric import DialogRetransmissionMetric
from glossogen.evaluation.metrics.english_ngram.backoff_ngram_metric import (
    EnglishNgramBackoffSurprisalMetric,
)
from glossogen.evaluation.metrics.english_ngram.english_ngram_metric import (
    EnglishNgramSurprisalMetric,
)
from glossogen.evaluation.metrics.gzip_compression_ratio_metric import GzipCompressionRatioMetric
from glossogen.evaluation.metrics.language_repetition_metric import LanguageRepetitionMetric
from glossogen.evaluation.metrics.language_strangeness_metric import LanguageStrangenessMetric
from glossogen.evaluation.metrics.mcm_metric import MCMMetric
from glossogen.evaluation.metrics.mcr_metric import MCRMetric
from glossogen.evaluation.metrics.message_entropy_metric import MessageEntropyMetric
from glossogen.evaluation.metrics.neologism_metric import NeologismMetric
from glossogen.evaluation.metrics.perplexity_metric import PerplexityMetric
from glossogen.evaluation.metrics.protocol_explanation_metric import ProtocolExplanationMetric
from glossogen.evaluation.metrics.protocol_learned_after_swap_metric import (
    ProtocolLearnedAfterSwapMetric,
)
from glossogen.evaluation.metrics.protocol_probe import (
    ProtocolProbeAgentPairSimilarityMetric,
    ProtocolProbeCutoffTrajectoryMetric,
    ProtocolProbeMetric,
    ProtocolProbeReplicaSelfSimilarityMetric,
)
from glossogen.evaluation.metrics.round_ended.postmortem_ended_timeout_metric import (
    PostmortemEndedTimeoutMetric,
)
from glossogen.evaluation.metrics.round_ended.round_ended_idle_metric import RoundEndedIdleMetric
from glossogen.evaluation.metrics.round_ended.round_ended_timeout_metric import (
    RoundEndedTimeoutMetric,
)
from glossogen.evaluation.metrics.round_success_after_resume_metric import (
    RoundSuccessAfterResumeMetric,
)
from glossogen.evaluation.metrics.round_success_metric import RoundSuccessMetric
from glossogen.evaluation.metrics.shorthand_codes_metric import ShorthandCodesMetric
from glossogen.evaluation.metrics.slang_emergence_metric import SlangEmergenceMetric
from glossogen.scenario_contract.protocol import SimulationScenario

logger = logging.getLogger(__name__)

_GENERIC_METRICS: list[type[Metric]] = [
    CommunicationFeaturePresenceMetric,
    CommunicationOpenCodingMetric,
    ContentFilterRefusalMetric,
    DialogRetransmissionMetric,
    EnglishNgramBackoffSurprisalMetric,
    EnglishNgramSurprisalMetric,
    GzipCompressionRatioMetric,
    LanguageRepetitionMetric,
    LanguageStrangenessMetric,
    MCMMetric,
    MCRMetric,
    MessageEntropyMetric,
    NeologismMetric,
    PerplexityMetric,
    PostmortemEndedTimeoutMetric,
    ProtocolExplanationMetric,
    ProtocolLearnedAfterSwapMetric,
    ProtocolProbeMetric,
    ProtocolProbeAgentPairSimilarityMetric,
    ProtocolProbeCutoffTrajectoryMetric,
    ProtocolProbeReplicaSelfSimilarityMetric,
    RoundEndedIdleMetric,
    RoundEndedTimeoutMetric,
    RoundSuccessAfterResumeMetric,
    RoundSuccessMetric,
    ShorthandCodesMetric,
    SlangEmergenceMetric,
]

GENERIC_METRIC_REGISTRY: dict[str, type[Metric]] = {cls.name: cls for cls in _GENERIC_METRICS}


def available_metrics(scenario_cls: type[SimulationScenario] | None) -> dict[str, type[Metric]]:
    """Return every metric that can be run on one scenario's runs.

    That is the generic metrics, the scenario's own ``scenario_metrics()``, and
    the ones other installed distributions declare. ``scenario_cls`` is None for
    a run whose scenario is no longer installed, which still has the generic and
    installed metrics.

    A generic metric wins a name collision, then the scenario's own, so an
    installed package cannot change what an existing metric name means: a report
    is keyed by metric name, and letting it be redefined would make two runs'
    reports incomparable. ``validate`` refuses a scenario metric that repeats a
    generic name, so that collision is logged here rather than raised.

    Importing external metric classes happens here, which is why listings that
    only need names call
    :func:`glossogen.evaluation.metric_core.scenario_metric_names.available_metric_names`
    instead.

    One unusable external metric is logged and skipped rather than failing the
    whole evaluation, so the metrics that do work still produce a report.
    """
    merged = dict(GENERIC_METRIC_REGISTRY)
    if scenario_cls is not None:
        for metric_cls in scenario_cls.scenario_metrics():
            if metric_cls.name in GENERIC_METRIC_REGISTRY:
                logger.error(
                    "Scenario %r declares metric %r, which repeats a generic metric's name; "
                    "ignoring the scenario's",
                    scenario_cls.name(),
                    metric_cls.name,
                )
                continue
            if metric_cls.name in merged:
                logger.error(
                    "Scenario %r declares metric %r more than once; keeping the first",
                    scenario_cls.name(),
                    metric_cls.name,
                )
                continue
            merged[metric_cls.name] = metric_cls
    for name, entry_point in external_metric_entry_points().items():
        if name in merged:
            logger.warning(
                "Metric %r is already provided by glossogen or the scenario; "
                "ignoring the one declared by %s",
                name,
                entry_point.value,
            )
            continue
        metric_cls = _load_external_metric(name=name, entry_point=entry_point)
        if metric_cls is None:
            continue
        merged[name] = metric_cls
    return merged


def _load_external_metric(name: str, entry_point: EntryPoint) -> type[Metric] | None:
    """Import one externally-declared metric, or return None if it is unusable.

    A class whose own ``name`` disagrees with the entry-point name is refused:
    the report is keyed by the class's ``name``, so accepting the mismatch would
    write a measurement under a name nobody asked for and nobody can look up.
    """
    try:
        candidate = entry_point.load()
    except Exception:
        logger.exception("Metric entry point %r (%s) failed to import", name, entry_point.value)
        return None
    if not isinstance(candidate, type) or not issubclass(candidate, Metric):
        logger.error(
            "Metric entry point %r (%s) does not name a Metric subclass; skipping it",
            name,
            entry_point.value,
        )
        return None
    if candidate.name != name:
        logger.error(
            "Metric entry point %r names a class whose own name is %r; skipping it. "
            "The entry-point name and the class's name attribute must match.",
            name,
            candidate.name,
        )
        return None
    return candidate
