"""Render yard containers into the strings agents read.

The spotter and planner both describe containers by attributes; these
helpers render a bundle the same way wherever it appears (injections, world
notifications, communication-rounds ground truth, run-detail panel) so every
surface is consistent.
"""

from schmidt.scenarios.container_yard_stacking.container_attributes import Container, render_inline


def render_container(container: Container) -> str:
    """Render a container's attribute bundle, e.g. ``red, large, tank, hazmat``."""
    return render_inline(container=container)
