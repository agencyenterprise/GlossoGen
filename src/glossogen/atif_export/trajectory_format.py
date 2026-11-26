"""``TrajectoryFormat``, the file formats that agent trajectories are exported in."""

from enum import Enum


class TrajectoryFormat(str, Enum):
    """The file format of an agent trajectory export.

    ``ATIF`` writes one ATIF document per agent. ``INSPECT`` writes one Inspect-format
    log with one sample per agent, the file that Docent's Upload Runs dialog imports.
    """

    ATIF = "atif"
    INSPECT = "inspect"
