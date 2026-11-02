"""The text the agent runner adds to an agent's conversation."""

from pydantic import BaseModel, ConfigDict


class RunnerPrompts(BaseModel):
    """What the runner appends to an agent's system prompt and sends as user prompts.

    ``system_suffix`` follows the scenario's base prompt and explains how to use
    the communication tools. ``initial`` opens the agent's first cycle and
    ``continuation`` every later one.

    ``closing`` is sent once the run has completed, after the agent's last turn,
    as one more user prompt in its own conversation. The agent may call no tool
    in reply, so it answers in text, and the runner logs the exchange as
    ``ClosingPromptAnswered``, or ``ClosingPromptFailed`` when no answer came
    back. None sends nothing. It defaults to None so the registrations logged
    before it existed still parse.
    """

    model_config = ConfigDict(frozen=True)

    system_suffix: str
    initial: str
    continuation: str
    closing: str | None = None
