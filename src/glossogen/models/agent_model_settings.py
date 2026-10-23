"""The model settings a run gives its simulation agents and its LLM judges.

``AgentModelSettings`` and ``JudgeModelSettings`` are the subset of pydantic-ai's
``ModelSettings`` a run may set, each field named and typed as pydantic-ai names
and types it. The agents' settings travel whole from the ``agent_model_settings``
knob to each agent's config, its ``AgentRegistered`` event, the runner and the
probe metrics. A judge's come from a scenario's ``judge_model_settings`` knob for
its round judge, and from ``evaluate --judge-settings`` for the evaluation judge.
Both extend ``ModelRequestSettings``, so adding a setting is adding a field there;
they differ only in the output cap, which an agent always sends and a judge sends
only when it is set.

It is a model of its own rather than ``ModelSettings`` itself because a run's
settings are recorded in its log and shown on its page: they have to be plain
JSON and reject keys nobody defined. That also leaves out the settings that would
break a run or leak from it: ``tool_choice`` (the runner relies on the model
picking its own tools) and ``extra_headers`` (a header could carry a credential
into a log that gets exported).
"""

from typing import cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from pydantic_ai.settings import ModelSettings, ServiceTier, ThinkingLevel

DEFAULT_AGENT_MAX_TOKENS = 16384


def _is_unset(value: object) -> bool:
    """Whether a setting is left out of the JSON: an unset one was not sent."""
    return value is None


class ModelRequestSettings(BaseModel):
    """The settings agents and judges share: every one but the output cap.

    Every field defaults to ``None``, which sends nothing and leaves the
    provider's own default in place. An unset field is also left out of the
    JSON, so a log records only what was sent. pydantic-ai documents each setting
    and which providers honour it; a provider that does not accept a value fails
    the call.

    ``thinking`` is how hard the model reasons: ``true``, ``false``, or one of
    ``minimal``, ``low``, ``medium``, ``high``, ``xhigh``, translated by
    pydantic-ai for each provider.

    ``timeout`` is in seconds. pydantic-ai also takes an httpx ``Timeout``, which
    has no JSON form.

    ``extra_body`` is merged into the request body as given, for a provider
    parameter pydantic-ai does not model. Nothing checks it.
    """

    model_config = ConfigDict(extra="forbid")

    thinking: ThinkingLevel | None = Field(default=None, exclude_if=_is_unset)
    temperature: float | None = Field(default=None, exclude_if=_is_unset)
    top_p: float | None = Field(default=None, exclude_if=_is_unset)
    top_k: int | None = Field(default=None, exclude_if=_is_unset)
    seed: int | None = Field(default=None, exclude_if=_is_unset)
    presence_penalty: float | None = Field(default=None, exclude_if=_is_unset)
    frequency_penalty: float | None = Field(default=None, exclude_if=_is_unset)
    logit_bias: dict[str, int] | None = Field(default=None, exclude_if=_is_unset)
    stop_sequences: list[str] | None = Field(default=None, exclude_if=_is_unset)
    service_tier: ServiceTier | None = Field(default=None, exclude_if=_is_unset)
    timeout: float | None = Field(default=None, gt=0, exclude_if=_is_unset)
    parallel_tool_calls: bool | None = Field(default=None, exclude_if=_is_unset)
    extra_body: dict[str, JsonValue] | None = Field(default=None, exclude_if=_is_unset)

    def to_pydantic_ai(self) -> ModelSettings:
        """Return the settings as pydantic-ai's ``ModelSettings``, leaving unset ones out.

        Every field shares its name with a ``ModelSettings`` key, so the dump is
        the mapping; an unset field is left out of it.
        """
        return cast(ModelSettings, self.model_dump())


class AgentModelSettings(ModelRequestSettings):
    """Settings sent with every request an agent makes.

    ``max_tokens`` caps one response, reasoning tokens included, and is always
    sent. The default is sized for thinking-capable models; self-hosted
    deployments served at a small fixed context often need it lower, since input
    plus ``max_tokens`` has to fit.
    """

    max_tokens: int = Field(default=DEFAULT_AGENT_MAX_TOKENS, ge=1)


class JudgeModelSettings(ModelRequestSettings):
    """Settings sent with every call an LLM judge makes.

    ``max_tokens`` is unset by default like every other field, so a judge's
    output is capped by the provider: on Anthropic, pydantic-ai sends the model's
    own maximum output; on OpenAI, the platform's provider default of 32768.
    """

    max_tokens: int | None = Field(default=None, ge=1, exclude_if=_is_unset)
