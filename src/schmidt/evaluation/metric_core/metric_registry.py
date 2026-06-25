"""Registry mapping metric names to their classes for generic metrics.

Generic metrics are scenario-agnostic and available to all scenarios. The
registry maps each metric's ``name`` to its zero-argument class so the
caller can instantiate with ``cls()`` and then pass per-invocation
``MetricRunOptions`` into ``cls.compute(...)``.
"""

from schmidt.evaluation.metric_core.metric_protocol import Metric
from schmidt.evaluation.metrics.communication.communication_feature_presence_metric import (
    CommunicationFeaturePresenceMetric,
)
from schmidt.evaluation.metrics.communication.communication_open_coding_metric import (
    CommunicationOpenCodingMetric,
)
from schmidt.evaluation.metrics.content_filter_refusal_metric import ContentFilterRefusalMetric
from schmidt.evaluation.metrics.dialog_retransmission_metric import DialogRetransmissionMetric
from schmidt.evaluation.metrics.english_ngram.english_ngram_metric import (
    EnglishNgramSurprisalMetric,
)
from schmidt.evaluation.metrics.gzip_compression_ratio_metric import GzipCompressionRatioMetric
from schmidt.evaluation.metrics.language_repetition_metric import LanguageRepetitionMetric
from schmidt.evaluation.metrics.language_strangeness_metric import LanguageStrangenessMetric
from schmidt.evaluation.metrics.mcm_metric import MCMMetric
from schmidt.evaluation.metrics.mcr_metric import MCRMetric
from schmidt.evaluation.metrics.message_entropy_metric import MessageEntropyMetric
from schmidt.evaluation.metrics.neologism_metric import NeologismMetric
from schmidt.evaluation.metrics.perplexity_metric import PerplexityMetric
from schmidt.evaluation.metrics.protocol_explanation_metric import ProtocolExplanationMetric
from schmidt.evaluation.metrics.protocol_learned_after_swap_metric import (
    ProtocolLearnedAfterSwapMetric,
)
from schmidt.evaluation.metrics.protocol_probe import (
    ProtocolProbeAgentPairSimilarityMetric,
    ProtocolProbeCutoffTrajectoryMetric,
    ProtocolProbeMetric,
    ProtocolProbeReplicaSelfSimilarityMetric,
)
from schmidt.evaluation.metrics.round_ended.round_ended_idle_metric import RoundEndedIdleMetric
from schmidt.evaluation.metrics.round_ended.round_ended_timeout_metric import (
    RoundEndedTimeoutMetric,
)
from schmidt.evaluation.metrics.round_success_after_resume_metric import (
    RoundSuccessAfterResumeMetric,
)
from schmidt.evaluation.metrics.round_success_metric import RoundSuccessMetric
from schmidt.evaluation.metrics.shorthand_codes_metric import ShorthandCodesMetric
from schmidt.evaluation.metrics.slang_emergence_metric import SlangEmergenceMetric

_GENERIC_METRICS: list[type[Metric]] = [
    CommunicationFeaturePresenceMetric,
    CommunicationOpenCodingMetric,
    ContentFilterRefusalMetric,
    DialogRetransmissionMetric,
    EnglishNgramSurprisalMetric,
    GzipCompressionRatioMetric,
    LanguageRepetitionMetric,
    LanguageStrangenessMetric,
    MCMMetric,
    MCRMetric,
    MessageEntropyMetric,
    NeologismMetric,
    PerplexityMetric,
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
