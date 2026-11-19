"""The pydantic-ai model that calls a self-hosted, OpenAI-compatible endpoint."""

from typing import ClassVar

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider


class SelfHostedChatModel(OpenAIChatModel):
    """An ``OpenAIChatModel`` that sends a system message only as a request's first message.

    vLLM renders each request with the served model's chat template, and Qwen3.8's template
    rejects a system message anywhere but first. With ``supports_inline_system_prompts`` off,
    pydantic-ai sends each later system prompt, such as its feedback after an empty response,
    as a user message wrapped in ``<system>`` tags. ``_announces_system_voice`` off keeps
    pydantic-ai from sending a second system message that explains the tag, so the request's
    one system message is the agent's prompt as written.

    ``openai_chat_supports_multiple_system_messages`` off makes pydantic-ai merge the
    system messages at the start of a request into one. If ``_announces_system_voice`` stops
    taking effect, the explanation then joins the agent's prompt instead of following it as a
    second system message.
    """

    _announces_system_voice: ClassVar[bool] = False

    def __init__(self, model_name: str, provider: OpenAIProvider) -> None:
        super().__init__(
            model_name=model_name,
            provider=provider,
            profile=OpenAIModelProfile(
                supports_inline_system_prompts=False,
                openai_chat_supports_multiple_system_messages=False,
            ),
        )
