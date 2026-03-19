"""Registry mapping evaluator names to their factory callables for generic evaluators.

Generic evaluators are scenario-agnostic and available to all scenarios.
"""

from schmidt.evaluation.cooperation_evaluator import CooperationEvaluator
from schmidt.evaluation.evaluator_protocol import EvaluatorFactory
from schmidt.evaluation.instruction_adherence import InstructionAdherenceEvaluator
from schmidt.evaluation.secret_leak_evaluator import SecretLeakEvaluator

GENERIC_EVALUATOR_REGISTRY: dict[str, EvaluatorFactory] = {
    "secret_leak": SecretLeakEvaluator,
    "instruction_adherence": InstructionAdherenceEvaluator,
    "cooperation": CooperationEvaluator,
}
