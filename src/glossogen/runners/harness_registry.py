"""The harnesses shipped here, by name.

Resolution goes through :mod:`glossogen.runners.harness_loader`, which also
reads the harnesses other installed distributions declare.
"""

from glossogen.runners.external_cli.claude_code import ClaudeCodeHarness
from glossogen.runners.external_cli.codex import CodexHarness
from glossogen.runners.harness_protocol import AgentHarness
from glossogen.runners.pydantic_ai_harness import PydanticAIHarness

HARNESS_REGISTRY: dict[str, type[AgentHarness]] = {
    PydanticAIHarness.name(): PydanticAIHarness,
    ClaudeCodeHarness.name(): ClaudeCodeHarness,
    CodexHarness.name(): CodexHarness,
}
