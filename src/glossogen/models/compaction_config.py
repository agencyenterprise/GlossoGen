"""Configuration for provider-native message-history compaction.

When enabled, the agent runner attaches the provider's compaction capability
(``AnthropicCompaction`` / ``OpenAICompaction``) so the provider summarizes older
messages once an agent's input tokens exceed ``token_threshold``, capping the
context re-read on every subsequent request. Disabled by default.
"""

from pydantic import BaseModel, ConfigDict


class CompactionConfig(BaseModel):
    """Whether to enable provider-native history compaction and its trigger threshold.

    ``token_threshold`` is the input-token count above which the provider compacts
    older messages into a summary. Anthropic enforces a minimum of 50,000.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    token_threshold: int = 50_000
