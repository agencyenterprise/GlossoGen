"""Evaluators for the persuasion debate scenario."""

from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.scenarios.persuasion_debate.evaluation.persuasion_accuracy_evaluator import (
    PersuasionAccuracyEvaluator,
)
from schmidt.scenarios.persuasion_debate.evaluation.persuasion_dynamics_evaluator import (
    PersuasionDynamicsEvaluator,
)

EVALUATOR_REGISTRY: dict[str, type[Evaluator]] = {
    "persuasion_accuracy": PersuasionAccuracyEvaluator,
    "persuasion_dynamics": PersuasionDynamicsEvaluator,
}

__all__ = ["EVALUATOR_REGISTRY", "PersuasionAccuracyEvaluator", "PersuasionDynamicsEvaluator"]
