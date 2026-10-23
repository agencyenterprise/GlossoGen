"""An ``LLMProvider`` that builds its real provider on the first call.

Building a judge builds its pydantic-ai model, which reads the provider's API
key and raises when it is missing, so building one is a live credential check.
Scenarios hold a judge provider, and they build it while constructing
themselves, which made constructing a scenario a credential check too. That is
wrong in three places that only ever want to *describe* a scenario:

- ``validate_run_config`` rebuilds the scenario to preflight a config, so
  validating a run under any provider demanded the judge's key as well.
- ``evaluate`` and the fork / resume flows rebuild scenarios from a recorded
  config to read their configuration back.
- The run-detail API rebuilds one to ask which channels it scores, on a server
  that otherwise needs no model access at all.

Deferring construction until the first ``generate_structured`` keeps the
credential check where it belongs: at the point of the call that needs it.
"""

from glossogen.evaluation.reports.evaluation_cost import (
    EvaluationCost,
    EvaluationTokenUsage,
    compute_evaluation_cost,
)
from glossogen.llm.provider import LLMMessage, LLMProvider, SamplingParams, T
from glossogen.llm.pydantic_ai_judge_provider import create_judge_provider
from glossogen.models.agent_model_settings import JudgeModelSettings


class DeferredLLMProvider(LLMProvider):
    """Wraps ``create_judge_provider`` so the real provider is built on first use."""

    def __init__(
        self,
        provider_name: str,
        model: str,
        inference_provider: str | None,
        settings: JudgeModelSettings,
    ) -> None:
        """Record the factory arguments without contacting any provider SDK."""
        super().__init__()
        self._provider_name = provider_name
        self._model = model
        self._inference_provider = inference_provider
        self._settings = settings
        self._delegate: LLMProvider | None = None

    def _resolve(self) -> LLMProvider:
        """Return the real provider, building it on the first call."""
        if self._delegate is None:
            self._delegate = create_judge_provider(
                provider_name=self._provider_name,
                model=self._model,
                inference_provider=self._inference_provider,
                settings=self._settings,
            )
        return self._delegate

    def get_accumulated_usage(self) -> EvaluationTokenUsage:
        """Return the delegate's usage, or zeros when no call has been made."""
        if self._delegate is None:
            return super().get_accumulated_usage()
        return self._delegate.get_accumulated_usage()

    def accumulated_cost(self) -> EvaluationCost:
        """Return what this judge's calls so far cost, priced under its model and provider."""
        return compute_evaluation_cost(
            usage=self.get_accumulated_usage(),
            model=self._model,
            provider_name=self._provider_name,
            model_settings=self._settings,
        )

    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        output_schema: type[T],
        sampling: SamplingParams | None = None,
    ) -> T:
        """Build the real provider if needed, then delegate the call to it."""
        return await self._resolve().generate_structured(
            system_prompt=system_prompt,
            messages=messages,
            output_schema=output_schema,
            sampling=sampling,
        )
