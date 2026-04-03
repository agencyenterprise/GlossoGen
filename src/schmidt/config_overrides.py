"""Hydra-style dot-notation config override parser.

Parses ``key=value`` strings from CLI arguments and applies them to a
nested config dict using dot-notation path resolution. The ``agents``
top-level key is reserved for per-agent model/provider overrides.
"""

import json
import logging
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)


class ConfigSplit(NamedTuple):
    """Result of splitting a merged config into scenario knobs and agent overrides."""

    scenario_config: dict[str, Any]
    agent_overrides: dict[str, dict[str, str]]


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
            target = target[part]
        target[parts[-1]] = parsed_value
        logger.info("Config override: %s = %r", dotted_key, parsed_value)
    return config


def split_agent_overrides(config: dict[str, Any]) -> ConfigSplit:
    """Extract the ``agents`` key from config as per-agent model overrides.

    Returns a ``ConfigSplit`` with the remaining scenario config and
    a dict mapping agent IDs to ``{"model": ..., "provider": ...}``.
    """
    agents_raw = config.pop("agents", {})
    agent_overrides: dict[str, dict[str, str]] = {}
    for agent_id, agent_conf in agents_raw.items():
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
