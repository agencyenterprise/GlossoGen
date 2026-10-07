"""Configuration for message-history compaction.

When enabled, the agent runner attaches the provider's compaction capability
(``AnthropicCompaction`` / ``OpenAICompaction``) so the provider summarizes older
messages once an agent's input tokens exceed ``token_threshold``, capping the
context re-read on every subsequent request. Self-hosted providers have no native
compaction, so the runner trims their history locally instead
(``ContextBudgetTrimmer``). Disabled by default.
"""

from pydantic import BaseModel, ConfigDict


class CompactionConfig(BaseModel):
    """Whether to enable provider-native history compaction and its trigger threshold.

    ``token_threshold`` is the input-token count above which the provider compacts
    older messages into a summary. Anthropic enforces a minimum of 50,000. For a
    self-hosted model, keep it below the server's max model length minus
    ``agent_max_tokens``.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    token_threshold: int = 50_000
