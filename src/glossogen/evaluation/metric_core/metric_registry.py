"""Registry mapping metric names to their classes.

Generic metrics are scenario-agnostic and available to all scenarios. The
registry maps each metric's ``name`` to its zero-argument class so the
caller can instantiate with ``cls()`` and then pass per-invocation
``MetricRunOptions`` into ``cls.compute(...)``.

``GENERIC_METRIC_REGISTRY`` holds the metrics shipped here.
:func:`available_metrics` adds the ones other installed distributions declare;
call that rather than reading the dict, unless you specifically mean the
built-in set.
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


def available_metrics() -> dict[str, type[Metric]]:
    """Return every metric that can be run, built-in and externally contributed.

    A metric shipped here wins a name collision, so an installed package cannot
    change what an existing metric name means: a report is keyed by metric name,
    and letting it be redefined would make two runs' reports incomparable.

    Importing external metric classes happens here. That is why the evaluation
    runner calls this and the scenario contract does not: a metric module imports
    the scenario contract, so the contract asks
    :mod:`glossogen.evaluation.metric_core.metric_entry_points` for names only.

    One unusable external metric is logged and skipped rather than failing the
    whole evaluation, so the metrics that do work still produce a report.
    """
    merged = dict(GENERIC_METRIC_REGISTRY)
    for name, entry_point in external_metric_entry_points().items():
        if name in merged:
            logger.warning(
                "Metric %r is already provided by glossogen; ignoring the one declared by %s",
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
