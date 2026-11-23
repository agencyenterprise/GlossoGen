"""The pydantic-ai model that calls a self-hosted, OpenAI-compatible endpoint."""

from typing import Any, ClassVar, cast

from openai.types import chat
from pydantic import BaseModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

# The ``provider_details`` keys that hold a response's token ids.
PROMPT_TOKEN_IDS_DETAIL = "prompt_token_ids"
TOKEN_IDS_DETAIL = "token_ids"


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

    When the request asked for token ids (vLLM's ``return_token_ids``), the response's
    ``prompt_token_ids`` and its first choice's ``token_ids`` are kept in the response's
    ``provider_details`` under ``PROMPT_TOKEN_IDS_DETAIL`` and ``TOKEN_IDS_DETAIL``.
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

    def _process_provider_details(self, response: chat.ChatCompletion) -> dict[str, Any] | None:
        """Add the response's token ids, when the server returned them, to pydantic-ai's details."""
        details = super()._process_provider_details(response)
        prompt_ids = _token_ids_field(model=response, name="prompt_token_ids")
        answer_ids = _token_ids_field(model=response.choices[0], name="token_ids")
        if prompt_ids is None or answer_ids is None:
            return details
        merged: dict[str, Any] = {}
        if details is not None:
            merged.update(details)
        merged[PROMPT_TOKEN_IDS_DETAIL] = prompt_ids
        merged[TOKEN_IDS_DETAIL] = answer_ids
        return merged


def _token_ids_field(model: BaseModel, name: str) -> list[int] | None:
    """Return a field that the OpenAI SDK kept as an extra, when it is a list of ints."""
    extra = model.model_extra
    if extra is None or name not in extra:
        return None
    value = extra[name]
    if not isinstance(value, list):
        return None
    ids = cast(list[object], value)
    if not all(isinstance(item, int) for item in ids):
        return None
    return cast(list[int], ids)
