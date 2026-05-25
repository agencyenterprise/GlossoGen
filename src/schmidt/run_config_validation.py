"""Shared validation helpers for scenario run configuration payloads."""

from typing import Any, NamedTuple, cast

from schmidt.config_overrides import normalize_agent_overrides, validate_agent_override_ids
from schmidt.scenario_protocol import SimulationScenario


class RunConfigValidationResult(NamedTuple):
    """Validated scenario config and optional normalized agent overrides."""

    scenario_config: dict[str, Any]
    normalized_agent_overrides: dict[str, dict[str, str]] | None


def validate_run_config(
    scenario_cls: type[SimulationScenario],
    scenario_config: dict[str, Any],
    default_provider: str,
    valid_providers: set[str],
) -> RunConfigValidationResult:
    """Prepare and validate scenario config and optional per-agent overrides."""
    prepared = scenario_cls.prepare_config(config=dict(scenario_config))
    scenario_cls.create_from_config(config=dict(prepared))

    raw_overrides = prepared.get("model_overrides")
    normalized: dict[str, dict[str, str]] | None = None
    if raw_overrides is not None:
        if not isinstance(raw_overrides, dict):
            raise SystemExit(
                "Invalid model_overrides: expected an object mapping "
                "agent IDs to override payloads."
            )
        normalized_input = _normalize_agent_override_input(
            agent_overrides=cast(dict[str, Any], raw_overrides)
        )
        normalized = normalize_agent_overrides(
            agent_overrides=normalized_input,
            default_provider=default_provider,
            valid_providers=valid_providers,
        )
        roles = scenario_cls.get_agent_roles(knobs=prepared)
        valid_agent_ids = {role.agent_id for role in roles}
        validate_agent_override_ids(
            agent_overrides=normalized,
            valid_agent_ids=valid_agent_ids,
        )
        prepared["model_overrides"] = normalized

    return RunConfigValidationResult(
        scenario_config=prepared,
        normalized_agent_overrides=normalized,
    )


def _normalize_agent_override_input(agent_overrides: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalize override entries into raw dict payloads."""
    normalized_input: dict[str, dict[str, Any]] = {}
    for agent_id, entry in agent_overrides.items():
        if isinstance(entry, dict):
            normalized_input[agent_id] = entry
            continue
        if hasattr(entry, "model_dump"):
            dumped = entry.model_dump()
            if isinstance(dumped, dict):
                normalized_input[agent_id] = dumped
                continue
        raise SystemExit(
            f"Invalid model_overrides.{agent_id}: expected a dict-like payload or Pydantic model."
        )
    return normalized_input
