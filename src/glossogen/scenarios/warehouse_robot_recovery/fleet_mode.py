"""The fleet traffic mode a warehouse round runs under."""

from enum import StrEnum


class FleetMode(StrEnum):
    """Traffic around the faulted robot, which decides the round's safety constraints."""

    NORMAL_TRAFFIC = "normal traffic"
    ELEVATED_TRAFFIC = "elevated traffic"
    HUMAN_PICK_PACK_ZONE_ACTIVE = "human pick-pack zone active"
