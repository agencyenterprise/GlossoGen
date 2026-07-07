"""Registry mapping metric names to their classes for generic metrics.

Generic metrics are scenario-agnostic and available to all scenarios. The
registry maps each metric's ``name`` to its zero-argument class so the
caller can instantiate with ``cls()`` and then pass per-invocation
``MetricRunOptions`` into ``cls.compute(...)``.
"""

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
