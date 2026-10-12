"""The harnesses shipped here, by name.

Resolution goes through :mod:`glossogen.runners.harness_loader`, which also
reads the harnesses other installed distributions declare.
"""

from glossogen.runners.claude_agent_sdk.harness import ClaudeAgentSdkHarness
from glossogen.runners.codex_app_server.harness import CodexAppServerHarness
from glossogen.runners.harness_protocol import AgentHarness
from glossogen.runners.pydantic_ai_harness import PydanticAIHarness

HARNESS_REGISTRY: dict[str, type[AgentHarness]] = {
    PydanticAIHarness.name(): PydanticAIHarness,
    ClaudeAgentSdkHarness.name(): ClaudeAgentSdkHarness,
    CodexAppServerHarness.name(): CodexAppServerHarness,
}
