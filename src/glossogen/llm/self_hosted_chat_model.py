"""The pydantic-ai model that calls a self-hosted, OpenAI-compatible endpoint."""

import math
from typing import Any, ClassVar, cast

from openai.types import chat
from pydantic import BaseModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

# The ``provider_details`` keys that hold a response's token ids and its answer's logprobs.
PROMPT_TOKEN_IDS_DETAIL = "prompt_token_ids"
TOKEN_IDS_DETAIL = "token_ids"
TOKEN_LOGPROBS_DETAIL = "token_logprobs"
# The key under which pydantic-ai keeps a response's logprobs with each token's text and bytes.
# A response with token ids keeps only the values, under ``TOKEN_LOGPROBS_DETAIL``.
PYDANTIC_AI_LOGPROBS_DETAIL = "logprobs"


# The logprob that vLLM gives a token whose logprob it does not have, and the floor it clamps to.
MISSING_LOGPROB = -9999.0


class TokenLogprobsMismatch(ValueError):
    """A response carries token ids but no logprobs, not one logprob per answer token, or a
    logprob that is not usable."""


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

    When the request asked for token ids (vLLM's ``return_token_ids``) and logprobs, the
    response's ``prompt_token_ids``, its first choice's ``token_ids`` and the logprob of each
    answer token are kept in the response's ``provider_details`` under
    ``PROMPT_TOKEN_IDS_DETAIL``, ``TOKEN_IDS_DETAIL`` and ``TOKEN_LOGPROBS_DETAIL``. A response
    with token ids and no usable logprob for each of its answer tokens raises
    :class:`TokenLogprobsMismatch`.
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
        """Add the response's token ids and answer logprobs to the details, when it has ids."""
        details = super()._process_provider_details(response)
        prompt_ids = _token_ids_field(model=response, name="prompt_token_ids")
        answer_ids = _token_ids_field(model=response.choices[0], name="token_ids")
        if prompt_ids is None or answer_ids is None:
            return details
        merged: dict[str, Any] = {}
        if details is not None:
            merged.update(details)
        merged.pop(PYDANTIC_AI_LOGPROBS_DETAIL, None)
        merged[PROMPT_TOKEN_IDS_DETAIL] = prompt_ids
        merged[TOKEN_IDS_DETAIL] = answer_ids
        merged[TOKEN_LOGPROBS_DETAIL] = answer_logprobs(
            choice=response.choices[0], token_ids=answer_ids
        )
        return merged


def answer_logprobs(choice: chat.chat_completion.Choice, token_ids: list[int]) -> list[float]:
    """Return the logprob of each answer token, one per id in ``token_ids``.

    An answer with no tokens may come without logprobs. Any other answer whose logprobs are
    missing or are not one per token id raises :class:`TokenLogprobsMismatch`. So does a
    logprob that is not a finite number, or that is at or below ``MISSING_LOGPROB``, vLLM's
    value for a logprob it does not have.
    """
    content = None
    if choice.logprobs is not None:
        content = choice.logprobs.content
    if content is None:
        if not token_ids:
            return []
        raise TokenLogprobsMismatch(
            f"The server returned {len(token_ids)} answer token ids and no logprobs"
        )
    values = [entry.logprob for entry in content]
    if len(values) != len(token_ids):
        raise TokenLogprobsMismatch(
            f"The server returned {len(values)} logprobs for {len(token_ids)} answer token ids"
        )
    unusable = sum(1 for value in values if not _usable_logprob(value=value))
    if unusable:
        raise TokenLogprobsMismatch(
            f"The server gave {unusable} of {len(values)} answer tokens no usable logprob "
            f"(not finite, or at or below {MISSING_LOGPROB})"
        )
    return values


def _usable_logprob(value: float) -> bool:
    """Whether a logprob is a finite number above vLLM's value for a missing logprob."""
    return math.isfinite(value) and value > MISSING_LOGPROB


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
