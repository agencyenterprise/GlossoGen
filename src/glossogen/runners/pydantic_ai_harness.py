"""The harness that drives a seat with pydantic-ai, the platform's default."""

from glossogen.runners.harness_names import PYDANTIC_AI_HARNESS_NAME
from glossogen.runners.harness_protocol import AgentHarness, HarnessSeat, RunnerBuildContext
from glossogen.runners.pydantic_ai_runner import PydanticAIRunner


class PydanticAIHarness(AgentHarness):
    """Builds ``PydanticAIRunner`` instances; needs nothing beyond the provider's credentials."""

    @classmethod
    def name(cls) -> str:
        return PYDANTIC_AI_HARNESS_NAME

    @classmethod
    def gates_model_responses(cls) -> bool:
        return True

    @classmethod
    def preflight(cls, seats: tuple[HarnessSeat, ...]) -> tuple[str, ...]:
        _ = seats
        return ()

    @classmethod
    def build_runner(cls, context: RunnerBuildContext) -> PydanticAIRunner:
        return PydanticAIRunner(
            max_turns=context.max_turns,
            event_bus=context.event_bus,
            run_id=context.run_id,
            scenario_name=context.scenario_name,
            telemetry_enabled=context.telemetry_enabled,
        )
