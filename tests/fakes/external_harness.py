"""Harnesses as another distribution would ship them, for the loader and launch-check tests."""

from glossogen.runners.agent_runner_base import AgentRunner
from glossogen.runners.harness_protocol import AgentHarness, HarnessSeat, RunnerBuildContext

EXTERNAL_HARNESS_NAME = "external-harness"
MISSING_BINARY_REMEDY = "install the external-harness binary"


class ExternalHarness(AgentHarness):
    """A harness that is ready, gates nothing, and is never asked to build a runner here."""

    @classmethod
    def name(cls) -> str:
        return EXTERNAL_HARNESS_NAME

    @classmethod
    def gates_model_responses(cls) -> bool:
        return False

    @classmethod
    def preflight(cls, seats: tuple[HarnessSeat, ...]) -> tuple[str, ...]:
        _ = seats
        return ()

    @classmethod
    def build_runner(cls, context: RunnerBuildContext) -> AgentRunner:
        raise NotImplementedError(f"the loader tests never build a runner ({context.run_id})")


class UnreadyExternalHarness(ExternalHarness):
    """A harness whose launch check names something the environment is missing."""

    @classmethod
    def preflight(cls, seats: tuple[HarnessSeat, ...]) -> tuple[str, ...]:
        _ = seats
        return (MISSING_BINARY_REMEDY,)


class NotAHarness:
    """An entry point target that does not implement the contract."""
