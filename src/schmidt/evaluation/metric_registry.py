"""Registry mapping metric names to their factory callables for generic metrics.

Generic metrics are scenario-agnostic and available to all scenarios.
"""

from schmidt.evaluation.content_filter_refusal_metric import ContentFilterRefusalMetric
from schmidt.evaluation.language_strangeness_metric import LanguageStrangenessMetric
from schmidt.evaluation.mcm_metric import MCMMetric
from schmidt.evaluation.mcr_metric import MCRMetric
from schmidt.evaluation.metric_protocol import Metric, MetricFactory
from schmidt.evaluation.neologism_metric import NeologismMetric
from schmidt.evaluation.perplexity_metric import PerplexityMetric
from schmidt.evaluation.round_ended_idle_metric import RoundEndedIdleMetric
from schmidt.evaluation.round_ended_timeout_metric import RoundEndedTimeoutMetric
from schmidt.evaluation.shorthand_codes_metric import ShorthandCodesMetric
from schmidt.evaluation.slang_emergence_metric import SlangEmergenceMetric

_GENERIC_METRICS: list[type[Metric]] = [
    ContentFilterRefusalMetric,
    LanguageStrangenessMetric,
    MCMMetric,
    MCRMetric,
    NeologismMetric,
    PerplexityMetric,
    RoundEndedIdleMetric,
    RoundEndedTimeoutMetric,
    ShorthandCodesMetric,
    SlangEmergenceMetric,
]

GENERIC_METRIC_REGISTRY: dict[str, MetricFactory] = {cls.name: cls for cls in _GENERIC_METRICS}
