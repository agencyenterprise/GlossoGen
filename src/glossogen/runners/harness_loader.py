"""Resolves harness names to classes for every caller.

Two sources feed it: the registry of harnesses shipped here, and harnesses
declared by other installed distributions under the versioned
``glossogen.agent_harnesses.v<N>`` entry-point group. A built-in name wins over
an external one declaring the same name, and the collision is logged.
"""

import logging
from importlib.metadata import EntryPoint

from glossogen.runners.harness_api import HARNESS_API_VERSION
from glossogen.runners.harness_entry_points import (
    HARNESS_ENTRY_POINT_GROUP,
    harness_declarations,
)
from glossogen.runners.harness_protocol import AgentHarness
from glossogen.runners.harness_registry import HARNESS_REGISTRY

logger = logging.getLogger(__name__)


def available_harness_names() -> list[str]:
    """Every harness name a seat can select, built-in and external, without importing any."""
    declarations = harness_declarations()
    for name, entry_point in declarations.current.items():
        if name in HARNESS_REGISTRY:
            logger.warning(
                "Harness %r is already provided by glossogen; ignoring the one declared by %s",
                name,
                entry_point.value,
            )
    for name, group in declarations.other_groups.items():
        logger.warning(
            "Harness %r is declared under entry-point group %r, which this glossogen "
            "does not read; it reads %r. Not listing it.",
            name,
            group,
            HARNESS_ENTRY_POINT_GROUP,
        )
    return sorted(set(HARNESS_REGISTRY) | set(declarations.current))


def get_harness_class(name: str) -> type[AgentHarness]:
    """The harness class registered under ``name``.

    Raises ValueError for a name nothing declares, one declared under a group
    this platform does not read, one whose entry point does not load into an
    ``AgentHarness`` subclass, or one whose class's ``name()`` disagrees with
    the entry point's name.
    """
    built_in = HARNESS_REGISTRY.get(name)
    if built_in is not None:
        return built_in
    declarations = harness_declarations()
    entry_point = declarations.current.get(name)
    if entry_point is not None:
        return _load_external(name=name, entry_point=entry_point)
    other_group = declarations.other_groups.get(name)
    if other_group is not None:
        raise ValueError(
            f"Harness '{name}' is installed, but declared under the entry-point group "
            f"'{other_group}', which this glossogen does not read. It reads "
            f"'{HARNESS_ENTRY_POINT_GROUP}' (harness contract version "
            f"{HARNESS_API_VERSION}). Upgrade whichever side is older, or correct the "
            "group name."
        )
    available = ", ".join(available_harness_names())
    raise ValueError(f"Unknown harness: '{name}'. Available harnesses: {available}")


def _load_external(name: str, entry_point: EntryPoint) -> type[AgentHarness]:
    """Import an externally declared harness class and check it names itself as declared."""
    try:
        loaded = entry_point.load()
    except Exception as exc:
        logger.exception("Harness entry point %r failed to import", name)
        raise ValueError(
            f"Harness entry point '{name}' ({entry_point.value}) failed to import: {exc}"
        ) from exc
    if not isinstance(loaded, type) or not issubclass(loaded, AgentHarness):
        raise ValueError(
            f"Harness entry point '{name}' ({entry_point.value}) "
            "does not name an AgentHarness subclass"
        )
    if loaded.name() != name:
        raise ValueError(
            f"Harness entry point '{name}' ({entry_point.value}) names itself "
            f"{loaded.name()!r}; the entry-point name and the class's name() must agree"
        )
    return loaded
