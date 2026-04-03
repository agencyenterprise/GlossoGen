"""Hydra-style dot-notation config override parser.

Parses ``key=value`` strings from CLI arguments and applies them to a
nested config dict using dot-notation path resolution. The ``agents``
top-level key is reserved for per-agent model/provider overrides.
"""

import json
import logging
from typing import Any, NamedTuple

from pydantic import BaseModel, ConfigDict, ValidationError

logger = logging.getLogger(__name__)


class ConfigSplit(NamedTuple):
    """Result of splitting a merged config into scenario knobs and agent overrides."""

    scenario_config: dict[str, Any]
    agent_overrides: dict[str, dict[str, str]]


class AgentOverridePayload(BaseModel):
    """Pydantic schema for one agent override payload."""

    model_config = ConfigDict(extra="forbid")

    model: str
    provider: str | None = None


def normalize_agent_overrides(
    agent_overrides: dict[str, dict[str, Any]],
    default_provider: str,
    valid_providers: set[str],
) -> dict[str, dict[str, str]]:
    """Validate and normalize per-agent overrides to {model, provider} strings."""
    normalized: dict[str, dict[str, str]] = {}
    for agent_id, override in agent_overrides.items():
        if not isinstance(override, dict):
            raise SystemExit(
                f"Invalid agents.{agent_id} override: expected an object with keys "
                "'model' and optional 'provider'."
            )
        try:
            payload = AgentOverridePayload.model_validate(override)
        except ValidationError as exc:
            raise SystemExit(f"Invalid agents.{agent_id} override: {exc}") from exc

        model_raw = payload.model
        if not isinstance(model_raw, str) or model_raw.strip() == "":
            raise SystemExit(f"Invalid agents.{agent_id}.model: expected a non-empty string.")
        model = model_raw.strip()

        provider_raw = payload.provider
        if provider_raw is None:
            provider_raw = default_provider
        if not isinstance(provider_raw, str) or provider_raw.strip() == "":
            raise SystemExit(f"Invalid agents.{agent_id}.provider: expected a non-empty string.")
        provider = provider_raw.strip()
        if provider not in valid_providers:
            raise SystemExit(
                f"Invalid agents.{agent_id}.provider: {provider!r}. "
                f"Supported providers: {sorted(valid_providers)}"
            )

        normalized[agent_id] = {"model": model, "provider": provider}
    return normalized


def validate_agent_override_ids(
    agent_overrides: dict[str, dict[str, str]],
    valid_agent_ids: set[str],
) -> None:
    """Validate that all per-agent overrides reference known agent IDs."""
    unknown = set(agent_overrides.keys()) - valid_agent_ids
    if unknown:
        raise SystemExit(
            f"agents.* overrides reference unknown agent IDs: {sorted(unknown)}. "
            f"Valid IDs: {sorted(valid_agent_ids)}"
        )


def parse_overrides(raw_args: list[str]) -> list[tuple[str, str]]:
    """Parse a list of ``key=value`` strings into (key, value) pairs.

    Raises SystemExit if any argument does not contain ``=``.
    """
    overrides: list[tuple[str, str]] = []
    for arg in raw_args:
        if "=" not in arg:
            raise SystemExit(
                f"Invalid override argument: {arg!r}. "
                "Expected format: key=value or dotted.key=value"
            )
        key, _, value = arg.partition("=")
        if key.startswith("--"):
            raise SystemExit(
                f"Invalid override argument: {arg!r}. "
                "Do not pass CLI flags in override position. "
                "Use config keys like max_round_duration_seconds=120."
            )
        _validate_dotted_key(key=key, raw_arg=arg)
        overrides.append((key, value))
    return overrides


def apply_overrides(config: dict[str, Any], overrides: list[tuple[str, str]]) -> dict[str, Any]:
    """Apply dot-notation overrides to a config dict.

    Each key is split on ``.`` to traverse nested dicts. Intermediate
    dicts are created when they do not exist. Values are auto-parsed
    as JSON; if parsing fails the raw string is used.
    """
    for dotted_key, raw_value in overrides:
        parsed_value = _parse_value(raw_value=raw_value)
        parts = dotted_key.split(".")
        target = config
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            elif not isinstance(target[part], dict):
                raise SystemExit(
                    f"Cannot apply override '{dotted_key}'. "
                    f"Path segment '{part}' points to a non-object value."
                )
            target = target[part]
            if not isinstance(target, dict):
                raise SystemExit(
                    f"Cannot apply override '{dotted_key}'. "
                    "Nested override path does not resolve to an object."
                )
        target[parts[-1]] = parsed_value
        logger.info("Config override: %s = %r", dotted_key, parsed_value)
    return config


def split_agent_overrides(config: dict[str, Any]) -> ConfigSplit:
    """Extract the ``agents`` key from config as per-agent model overrides.

    Returns a ``ConfigSplit`` with the remaining scenario config and
    a dict mapping agent IDs to ``{"model": ..., "provider": ...}``.
    """
    agents_raw = config.pop("agents", {})
    if not isinstance(agents_raw, dict):
        raise SystemExit(
            "Invalid config key 'agents': expected an object mapping "
            "agent IDs to override objects."
        )
    agent_overrides: dict[str, dict[str, str]] = {}
    for agent_id, agent_conf in agents_raw.items():
        if not isinstance(agent_id, str) or not agent_id:
            raise SystemExit("Invalid agent override key under 'agents': expected non-empty string")
        if isinstance(agent_conf, dict):
            agent_overrides[agent_id] = agent_conf
        else:
            agent_overrides[agent_id] = {"model": str(agent_conf)}
    return ConfigSplit(
        scenario_config=config,
        agent_overrides=agent_overrides,
    )


def _parse_value(raw_value: str) -> Any:
    """Attempt to parse a string as JSON, falling back to the raw string.

    This lets users write ``rounds=5`` (parsed as int), ``enabled=true``
    (parsed as bool), or ``name=alice`` (kept as string).
    """
    try:
        return json.loads(raw_value)
    except (json.JSONDecodeError, ValueError):
        return raw_value


def _validate_dotted_key(key: str, raw_arg: str) -> None:
    """Validate dotted override key syntax."""
    if key == "":
        raise SystemExit(f"Invalid override argument: {raw_arg!r}. " "Key cannot be empty.")
    parts = key.split(".")
    if any(part == "" for part in parts):
        raise SystemExit(
            f"Invalid override argument: {raw_arg!r}. "
            "Dotted keys cannot contain empty path segments."
        )
