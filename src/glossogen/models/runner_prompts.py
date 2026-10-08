"""The text the agent runner adds to an agent's conversation."""

from pydantic import BaseModel, ConfigDict


class RunnerPrompts(BaseModel):
    """What the runner appends to an agent's system prompt and sends as user prompts.

    ``system_suffix`` follows the scenario's base prompt and explains how to use
    the communication tools. ``initial`` opens the agent's first cycle and
    ``continuation`` every later one.
    """

    model_config = ConfigDict(frozen=True)

    system_suffix: str
    initial: str
    continuation: str
