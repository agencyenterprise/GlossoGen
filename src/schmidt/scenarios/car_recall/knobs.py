"""Configuration knobs for the car recall scenario.

Defines the tunable parameters that control scenario behavior:
time pressure, goal alignment, regulator pressure, agent count,
and information overlap.
"""

from enum import Enum
from typing import Self

from pydantic import BaseModel, model_validator


class TimePressure(str, Enum):
    """Controls the number of simulation rounds.

    LOW runs 5 rounds (days 1-5). HIGH compresses to 3 rounds
    (days 1, 3, 5), skipping intermediate escalation events.
    """

    LOW = "low"
    HIGH = "high"


class GoalAlignment(str, Enum):
    """Controls whether agents prioritize company or department interests.

    LOW means all agents optimize for the company's overall outcome.
    HIGH means each agent protects their own department's budget and reputation.
    """

    LOW = "low"
    HIGH = "high"


class RegulatorPressure(str, Enum):
    """Controls how aggressively the Regulator probes for information.

    LOW means routine, vague questioning. HIGH means the Regulator hints
    at having inside information (anonymous tip), pressing harder for disclosure.
    """

    LOW = "low"
    HIGH = "high"


class AgentCount(str, Enum):
    """Controls how many agents participate in the simulation.

    THREE includes Engineer, Legal, and PR only (no CFO or Regulator).
    FIVE includes all agents: Engineer, Legal, CFO, PR, and Regulator.
    """

    THREE = "three"
    FIVE = "five"


class InformationOverlap(str, Enum):
    """Controls whether agents have hints about other agents' private facts.

    LOW means each agent only knows their own confidential information.
    HIGH means agents have vague rumors about what others might know.
    """

    LOW = "low"
    HIGH = "high"


class CarRecallKnobs(BaseModel):
    """Configuration knobs for the car recall scenario.

    Each field controls one dimension of scenario behavior. All fields
    are required — callers must explicitly set every knob.
    """

    time_pressure: TimePressure
    goal_alignment: GoalAlignment
    regulator_pressure: RegulatorPressure
    agent_count: AgentCount
    information_overlap: InformationOverlap

    @model_validator(mode="after")
    def validate_knob_combinations(self) -> Self:
        """Validate that knob combinations are consistent."""
        if (
            self.agent_count == AgentCount.THREE
            and self.regulator_pressure == RegulatorPressure.HIGH
        ):
            raise ValueError(
                "regulator_pressure cannot be HIGH when agent_count is THREE "
                "(no Regulator agent exists in 3-agent mode)"
            )

        return self
