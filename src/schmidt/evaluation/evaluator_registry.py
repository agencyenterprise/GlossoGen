"""Registry mapping evaluator names to their factory callables for generic evaluators.

Generic evaluators are scenario-agnostic and available to all scenarios.
"""

from schmidt.evaluation.evaluator_protocol import Evaluator, EvaluatorFactory
from schmidt.evaluation.secret_leak_evaluator import SecretLeakEvaluator

_GENERIC_EVALUATORS: list[type[Evaluator]] = [
    SecretLeakEvaluator,
]

GENERIC_EVALUATOR_REGISTRY: dict[str, EvaluatorFactory] = {
    cls.name: cls for cls in _GENERIC_EVALUATORS
}
