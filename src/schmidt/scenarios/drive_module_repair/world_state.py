"""Immutable per-round outcome type for the drive_module_repair world."""

from typing import NamedTuple


class DriveModuleOutcome(NamedTuple):
    """Result of a single drive-module case after a round completes."""

    case_number: int
    replacement_count: int
    replacements_done: int
    budget_exceeded: bool
    characters_used: int
    round_time_budget_seconds: int
    device_repaired: bool
    round_succeeded: bool
    failure_reason: str
