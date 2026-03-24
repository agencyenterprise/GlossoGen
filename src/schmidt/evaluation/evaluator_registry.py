"""Registry mapping evaluator names to their classes for generic evaluators.

Generic evaluators are scenario-agnostic and available to all scenarios.
"""

from schmidt.evaluation.communication_pattern_evaluator import CommunicationPatternEvaluator
from schmidt.evaluation.cooperation_evaluator import CooperationEvaluator
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.instruction_adherence import InstructionAdherenceEvaluator
from schmidt.evaluation.secret_leak_evaluator import SecretLeakEvaluator

GENERIC_EVALUATOR_REGISTRY: dict[str, type[Evaluator]] = {
    "secret_leak": SecretLeakEvaluator,
    "instruction_adherence": InstructionAdherenceEvaluator,
    "cooperation": CooperationEvaluator,
    "communication_pattern": CommunicationPatternEvaluator,
}
