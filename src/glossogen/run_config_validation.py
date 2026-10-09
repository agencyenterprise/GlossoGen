"""Shared validation helpers for scenario run configuration payloads."""

from typing import Any, NamedTuple, cast

from glossogen.config_overrides import (
    ResolvedAgentModel,
    model_overrides_config_value,
    normalize_agent_overrides,
    validate_agent_override_ids,
)
from glossogen.model_catalog import Provider
from glossogen.scenario_protocol import SimulationScenario


class RunConfigValidationResult(NamedTuple):
    """Validated scenario config and optional normalized agent overrides."""

    scenario_config: dict[str, Any]
    normalized_agent_overrides: dict[str, ResolvedAgentModel] | None


def validate_run_config(
    scenario_cls: type[SimulationScenario],
    scenario_config: dict[str, Any],
    default_provider: str,
    valid_providers: set[Provider],
) -> RunConfigValidationResult:
    """Prepare and validate scenario config and optional per-agent overrides."""
    prepared = scenario_cls.prepare_config(config=dict(scenario_config))
    scenario = scenario_cls.create_from_config(config=dict(prepared))
    # Read at run time by direct-channel routing and by the metrics. A scenario
    # from another distribution built against an older ``PrimaryChannel`` fails
    # here, before a run directory is claimed, rather than at evaluation.
    scenario.get_primary_channels()

    raw_overrides = prepared.get("model_overrides")
    normalized: dict[str, ResolvedAgentModel] | None = None
    if raw_overrides is not None:
        if not isinstance(raw_overrides, dict):
            raise SystemExit(
                "Invalid model_overrides: expected an object mapping "
                "agent IDs to override payloads."
            )
        normalized = normalize_agent_overrides(
            agent_overrides=cast(dict[str, object], raw_overrides),
            default_provider=default_provider,
            valid_providers=valid_providers,
        )
        roles = scenario_cls.get_agent_roles(knobs=prepared)
        valid_agent_ids = {role.agent_id for role in roles}
        validate_agent_override_ids(
            agent_overrides=normalized,
            valid_agent_ids=valid_agent_ids,
        )
        prepared["model_overrides"] = model_overrides_config_value(overrides=normalized)

    return RunConfigValidationResult(
        scenario_config=prepared,
        normalized_agent_overrides=normalized,
    )
