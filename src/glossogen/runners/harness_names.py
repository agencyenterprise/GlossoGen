"""The names of the harnesses shipped here.

A harness is the thing that drives one agent's model loop. Its name is what a
seat records on ``AgentRegistered`` and what ``--harness`` and
``agents.<id>.harness=`` select. This module holds only strings, so the models
package can name the default without importing a runner.
"""

PYDANTIC_AI_HARNESS_NAME = "pydantic-ai"
CLAUDE_CODE_HARNESS_NAME = "claude-code"
CODEX_HARNESS_NAME = "codex"

HARNESS_STATE_DIR_NAME = "harness_state"
"""The directory under a seat's directory where a harness keeps private working
state, such as a CLI's configuration directory. Run archives never carry it."""
