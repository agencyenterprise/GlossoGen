"""Configuration knobs for the persuasion debate scenario.

Defines the tunable parameters: debate mode, agent order, persuasion strategy,
round count, turn limits, and per-agent model overrides.
"""

from enum import Enum
from typing import Self

from pydantic import BaseModel, model_validator


class DebateMode(str, Enum):
    """Controls the type of persuasion evaluation.

    MISINFORMATION: adversary tries to flip target's correct answer to incorrect.
    BALANCED: 50% negative persuasion + 50% positive persuasion tests.
    DEBATE: two models of different strengths debate genuinely.
    """

    MISINFORMATION = "misinformation"
    BALANCED = "balanced"
    DEBATE = "debate"


class AgentOrder(str, Enum):
    """Controls which agent answers first each round.

    A_FIRST means agent_a states their answer before agent_b sees it.
    B_FIRST means agent_b states their answer before agent_a sees it.
    """

    A_FIRST = "a_first"
    B_FIRST = "b_first"


class PersuasionStrategy(str, Enum):
    """The persuasion approach used by the adversary agent in misinformation mode.

    LOGICAL: argue using logical reasoning and evidence.
    EMOTIONAL: use emotional appeals to convince.
    CREDIBLE: establish credibility and expertise.
    """

    LOGICAL = "logical"
    EMOTIONAL = "emotional"
    CREDIBLE = "credible"


VALID_AGENT_IDS = {"agent_a", "agent_b"}


class PersuasionDebateKnobs(BaseModel):
    """Configuration knobs for the persuasion debate scenario."""

    mode: DebateMode
    agent_order: AgentOrder
    round_count: int
    max_turns_per_round: int
    persuasion_strategy: PersuasionStrategy
    model_overrides: dict[str, str]

    @model_validator(mode="after")
    def validate_knob_combinations(self) -> Self:
        """Validate that model override keys are valid agent IDs."""
        unknown = set(self.model_overrides.keys()) - VALID_AGENT_IDS
        if unknown:
            raise ValueError(
                f"model_overrides contains unknown agent IDs: {unknown}. "
                f"Valid IDs: {sorted(VALID_AGENT_IDS)}"
            )
        return self
