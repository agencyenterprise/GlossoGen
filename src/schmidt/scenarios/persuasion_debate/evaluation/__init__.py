"""Evaluators for the persuasion debate scenario."""

from schmidt.evaluation.evaluator_protocol import EvaluatorFactory
from schmidt.scenarios.persuasion_debate.evaluation.persuasion_accuracy_evaluator import (
    PersuasionAccuracyEvaluator,
)
from schmidt.scenarios.persuasion_debate.evaluation.persuasion_dynamics_evaluator import (
    PersuasionDynamicsEvaluator,
)

EVALUATOR_REGISTRY: dict[str, EvaluatorFactory] = {
    PersuasionAccuracyEvaluator.name: PersuasionAccuracyEvaluator,
    PersuasionDynamicsEvaluator.name: PersuasionDynamicsEvaluator,
}

__all__ = ["EVALUATOR_REGISTRY", "PersuasionAccuracyEvaluator", "PersuasionDynamicsEvaluator"]
