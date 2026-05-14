"""Shared type for the ``protocol_learned_after_swap`` metric.

``ProtocolBoundaryWindow`` describes the round split around a single
personnel-change boundary: which round closes the pre-boundary
window, which round opens the post-boundary window, and whether the
boundary round itself counts as pre or post. The metric reads this
to decide which rounds the LLM judge sees as "before" vs "after" the
newcomer joined.

Returned by ``SimulationScenario.detect_protocol_boundary_window``,
which centralises scenario-specific boundary detection (intern
takeover, two-team observer swap, scheduled in-run swap).
"""

from typing import NamedTuple


class ProtocolBoundaryWindow(NamedTuple):
    """The split around one personnel-change boundary.

    ``mode_label`` is a short identifier rendered into the judge prompt
    (e.g. ``"intern"``, ``"swap"``, ``"scheduled_swap"``).
    ``boundary_round`` is the round at which the change takes effect.
    ``pre_boundary_last_round`` and ``post_boundary_first_round``
    delimit the inclusive pre/post windows. ``boundary_includes_round``
    is True when the boundary round itself is part of the post-boundary
    window (intern / scheduled-swap, where the newcomer is active for
    that round) and False when it stays in the pre-boundary window
    (two-team swap, where the swap fires after the round completes).
    ``newcomer_label`` is a human-readable description of who took over,
    used in the judge prompt to help interpret the post-boundary
    transcript.
    """

    mode_label: str
    boundary_round: int
    pre_boundary_last_round: int
    post_boundary_first_round: int
    newcomer_label: str
    boundary_includes_round: bool
