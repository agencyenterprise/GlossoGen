"""The names of the harnesses shipped here.

A harness is the thing that drives one agent's model loop. Its name is what a
seat records on ``AgentRegistered`` and what ``--harness`` and
``agents.<id>.harness=`` select. This module holds only strings, so the models
package can name the default without importing a runner.
"""

PYDANTIC_AI_HARNESS_NAME = "pydantic-ai"
CLAUDE_AGENT_SDK_HARNESS_NAME = "claude-agent-sdk"
CODEX_HARNESS_NAME = "codex"

HARNESS_STATE_DIR_NAME = "harness_state"
"""The directory under a seat's directory where a harness keeps private working
state. Run archives never carry it."""
