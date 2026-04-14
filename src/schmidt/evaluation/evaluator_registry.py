"""Registry mapping evaluator names to their factory callables for generic evaluators.

Generic evaluators are scenario-agnostic and available to all scenarios.
They focus on detecting language emergence phenomena in agent communication.
"""

from schmidt.evaluation.evaluator_protocol import Evaluator, EvaluatorFactory
from schmidt.evaluation.language_strangeness_evaluator import LanguageStrangenessEvaluator
from schmidt.evaluation.neologism_evaluator import NeologismEvaluator
from schmidt.evaluation.shorthand_codes_evaluator import ShorthandCodesEvaluator
from schmidt.evaluation.slang_emergence_evaluator import SlangEmergenceEvaluator

_GENERIC_EVALUATORS: list[type[Evaluator]] = [
    LanguageStrangenessEvaluator,
    NeologismEvaluator,
    ShorthandCodesEvaluator,
    SlangEmergenceEvaluator,
]

GENERIC_EVALUATOR_REGISTRY: dict[str, EvaluatorFactory] = {
    cls.name: cls for cls in _GENERIC_EVALUATORS
}
