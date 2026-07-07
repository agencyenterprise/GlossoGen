"""Attribute schema for yard containers plus rendering helpers.

A container has no ID; it is defined entirely by a bundle of categorical
attributes (one value per dimension in ``ATTRIBUTE_NAMES``). Agents must
describe a container by its attributes rather than relay an opaque label.
The helpers here render a bundle for prompts; the spotter and planner must
converge on a shared compact code for these bundles so the (attribute-blind)
crane can join their reports.
"""

from typing import NamedTuple

ATTRIBUTE_NAMES: tuple[str, ...] = ("colour", "size", "type", "marking")

ATTRIBUTE_VALUES: dict[str, tuple[str, ...]] = {
    "colour": ("red", "blue", "green", "yellow", "black", "white", "orange", "teal"),
    "size": ("small", "medium", "large"),
    "type": ("standard", "reefer", "tank", "flatrack", "opentop", "insulated"),
    "marking": ("plain", "hazmat", "fragile", "priority"),
}


class Container(NamedTuple):
    """One yard container: an ordered value per dimension in ``ATTRIBUTE_NAMES``."""

    values: tuple[str, ...]


def attribute_pairs(container: Container) -> list[tuple[str, str]]:
    """Return ``container`` as an ordered list of (attribute_name, value) pairs."""
    return list(zip(ATTRIBUTE_NAMES, container.values))


def render_inline(container: Container) -> str:
    """Render a container as a comma-joined value list, e.g. ``red, large, tank, hazmat``."""
    return ", ".join(container.values)
