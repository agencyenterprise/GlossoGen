"""Configuration knobs for the persuasion debate scenario.

Defines the tunable parameters: debate mode, agent ordering, belief assignments,
persuasion strategy, round count, turn limits, and per-agent model overrides.
"""

from enum import Enum
from typing import Self

from pydantic import BaseModel, model_validator

from schmidt.scenarios.persuasion_debate.agent_ids import ALL_AGENT_IDS


class DebateMode(str, Enum):
    """Controls the type of persuasion evaluation.

    MISINFORMATION: adversary tries to flip target's correct answer to incorrect.
    BALANCED: 50% negative persuasion + 50% positive persuasion tests.
    DEBATE: open-ended debate with no seeded answers.
    SEEDED_DEBATE: open-ended debate with seeded answers per agent_beliefs.
    """

    MISINFORMATION = "misinformation"
    BALANCED = "balanced"
    DEBATE = "debate"
    SEEDED_DEBATE = "seeded_debate"


class PersuasionStrategy(str, Enum):
    """The persuasion approach used by the adversary agent in misinformation mode.

    LOGICAL: argue using logical reasoning and evidence.
    EMOTIONAL: use emotional appeals to convince.
    CREDIBLE: establish credibility and expertise.
    """

    LOGICAL = "logical"
    EMOTIONAL = "emotional"
    CREDIBLE = "credible"


class BeliefAssignment(str, Enum):
    """Controls which answer an agent is seeded with in seeded_debate mode.

    CORRECT: agent receives the reference (correct) answer.
    WRONG: agent receives the wrong (plausible but incorrect) answer.
    """

    CORRECT = "correct"
    WRONG = "wrong"


class PersuasionDebateKnobs(BaseModel):
    """Configuration knobs for the persuasion debate scenario."""

    mode: DebateMode
    agent_order: list[str]
    round_count: int
    max_turns_per_round: int
    persuasion_strategy: PersuasionStrategy | None
    model_overrides: dict[str, str]
    agent_beliefs: dict[str, BeliefAssignment] | None

    @model_validator(mode="after")
    def validate_knob_combinations(self) -> Self:
        """Validate agent ordering, model overrides, beliefs, and strategy requirements."""
        order_set = set(self.agent_order)
        if len(order_set) != len(self.agent_order):
            raise ValueError("agent_order contains duplicate agent IDs")

        unknown_order = order_set - ALL_AGENT_IDS
        if unknown_order:
            raise ValueError(
                f"agent_order contains unknown agent IDs: {unknown_order}. "
                f"Valid IDs: {sorted(ALL_AGENT_IDS)}"
            )

        unknown_overrides = set(self.model_overrides.keys()) - order_set
        if unknown_overrides:
            raise ValueError(
                f"model_overrides references agents not in agent_order: {unknown_overrides}"
            )

        needs_strategy = {DebateMode.MISINFORMATION, DebateMode.BALANCED}
        if self.mode in needs_strategy and self.persuasion_strategy is None:
            raise ValueError(f"persuasion_strategy is required for mode '{self.mode.value}'")

        if self.agent_beliefs is not None:
            beliefs_keys = set(self.agent_beliefs.keys())
            if beliefs_keys != order_set:
                raise ValueError(
                    f"agent_beliefs keys {sorted(beliefs_keys)} must match "
                    f"agent_order {self.agent_order}"
                )

        return self
