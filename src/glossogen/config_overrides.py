"""Hydra-style dot-notation config override parser.

Parses ``key=value`` strings from CLI arguments and applies them to a
nested config dict using dot-notation path resolution. The ``agents``
top-level key is reserved for per-agent model/provider overrides.
"""

import json
import logging
from collections.abc import Mapping
from typing import Any, NamedTuple, cast

from pydantic import ValidationError

from glossogen.model_catalog import Provider
from glossogen.scenarios.base_knobs import AgentModelOverride

logger = logging.getLogger(__name__)


class ResolvedAgentModel(NamedTuple):
    """The model and provider one agent runs under once its override is resolved."""

    model: str
    provider: Provider

    def as_config_entry(self) -> dict[str, str]:
        """Return the JSON shape a ``model_overrides`` entry records in a config."""
        return {"model": self.model, "provider": self.provider.value}


def model_overrides_config_value(
    overrides: Mapping[str, ResolvedAgentModel],
) -> dict[str, dict[str, str]]:
    """Return ``overrides`` in the JSON shape a config's ``model_overrides`` records."""
    return {agent_id: resolved.as_config_entry() for agent_id, resolved in overrides.items()}


class ConfigSplit(NamedTuple):
    """Result of splitting a merged config into scenario knobs and agent overrides."""

    scenario_config: dict[str, Any]
    agent_overrides: dict[str, AgentModelOverride]


def normalize_agent_overrides(
    agent_overrides: Mapping[str, object],
    default_provider: str,
    valid_providers: set[Provider],
) -> dict[str, ResolvedAgentModel]:
    """Validate per-agent overrides and resolve a missing provider to ``default_provider``.

    Each entry is a raw payload or an ``AgentModelOverride``. Raises
    ``SystemExit`` for an entry that does not validate or whose provider is
    not in ``valid_providers``.
    """
    normalized: dict[str, ResolvedAgentModel] = {}
    for agent_id, override in agent_overrides.items():
        try:
            payload = AgentModelOverride.model_validate(override)
        except ValidationError as exc:
            logger.exception("Invalid agents.%s override", agent_id)
            raise SystemExit(f"Invalid agents.{agent_id} override: {exc}") from exc
        provider = _resolve_override_provider(
            agent_id=agent_id,
            provider=payload.provider,
            default_provider=default_provider,
        )
        if provider not in valid_providers:
            raise SystemExit(
                f"Invalid agents.{agent_id}.provider: {provider.value!r}. "
                f"Supported providers: {sorted(valid_providers)}"
            )
        normalized[agent_id] = ResolvedAgentModel(model=payload.model, provider=provider)
    return normalized


def _resolve_override_provider(
    agent_id: str,
    provider: Provider | None,
    default_provider: str,
) -> Provider:
    """Return ``provider``, or ``default_provider`` when the override names none."""
    if provider is not None:
        return provider
    try:
        return Provider(default_provider)
    except ValueError as exc:
        logger.exception("Unknown default provider for agents.%s", agent_id)
        raise SystemExit(
            f"Invalid agents.{agent_id}.provider: the default provider "
            f"{default_provider!r} is not a known provider."
        ) from exc


def validate_agent_override_ids(
    agent_overrides: Mapping[str, ResolvedAgentModel],
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
        target: dict[str, Any] = config
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            next_target = target[part]
            if not isinstance(next_target, dict):
                raise SystemExit(
                    f"Cannot apply override '{dotted_key}'. "
                    f"Path segment '{part}' points to a non-object value."
                )
            target = cast(dict[str, Any], next_target)
        target[parts[-1]] = parsed_value
        logger.info("Config override: %s = %r", dotted_key, parsed_value)
    return config


def split_agent_overrides(config: dict[str, Any]) -> ConfigSplit:
    """Extract the ``agents`` key from config as per-agent model overrides.

    Returns a ``ConfigSplit`` with the remaining scenario config and each
    agent's validated ``AgentModelOverride``. A bare string value
    (``agents.observer=gpt-5.4``) sets only the model.
    """
    agents_raw_obj = config.pop("agents", {})
    if not isinstance(agents_raw_obj, dict):
        raise SystemExit(
            "Invalid config key 'agents': expected an object mapping "
            "agent IDs to override objects."
        )
    agents_raw = cast(dict[Any, Any], agents_raw_obj)
    agent_overrides: dict[str, AgentModelOverride] = {}
    for agent_id, agent_conf in agents_raw.items():
        if not isinstance(agent_id, str) or not agent_id:
            raise SystemExit("Invalid agent override key under 'agents': expected non-empty string")
        agent_overrides[agent_id] = _parse_agent_override(agent_id=agent_id, agent_conf=agent_conf)
    return ConfigSplit(
        scenario_config=config,
        agent_overrides=agent_overrides,
    )


def _parse_agent_override(agent_id: str, agent_conf: object) -> AgentModelOverride:
    """Validate one ``agents.<id>`` value, reading a bare string as the model name."""
    if isinstance(agent_conf, str):
        payload: object = {"model": agent_conf}
    else:
        payload = agent_conf
    try:
        return AgentModelOverride.model_validate(payload)
    except ValidationError as exc:
        logger.exception("Invalid agents.%s override", agent_id)
        raise SystemExit(f"Invalid agents.{agent_id} override: {exc}") from exc


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
