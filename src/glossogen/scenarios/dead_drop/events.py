"""dead_drop's own events: the case, filesystem activity, answers and verdicts."""

from typing import Literal

from pydantic import BaseModel

from glossogen.models.event_base import EventBase
from glossogen.scenarios.dead_drop.ids import FsOperation


class AgentCaseRecord(BaseModel):
    """One agent's half of a round: the codebook it holds and the keys it must answer."""

    agent_id: str
    codebook: dict[str, str]
    requests: list[str]


class DeadDropCaseStarted(EventBase):
    """A round's case, written into each home as the round opens."""

    event_type: Literal["dead_drop_case_started"] = "dead_drop_case_started"
    cases: list[AgentCaseRecord]


class DeadDropFsChanged(EventBase):
    """One change an agent made to the filesystem, in the order it was made.

    ``path`` is the path the agent named and ``destination`` the second path of a
    copy or move. ``content`` is what a write or append wrote, ``mode`` what a
    chmod set. ``shared`` is true when the change landed where the other agent
    can read it. Replaying these in order rebuilds the filesystem.
    """

    event_type: Literal["dead_drop_fs_changed"] = "dead_drop_fs_changed"
    agent_id: str
    operation: FsOperation
    path: str
    destination: str | None
    content: str | None
    mode: int | None
    recursive: bool
    shared: bool


class DeadDropFsRead(EventBase):
    """An agent read a file: what it read and who wrote that content."""

    event_type: Literal["dead_drop_fs_read"] = "dead_drop_fs_read"
    agent_id: str
    path: str
    authors: list[str]
    content: str
    shared: bool


class DeadDropFsListed(EventBase):
    """An agent listed a directory."""

    event_type: Literal["dead_drop_fs_listed"] = "dead_drop_fs_listed"
    agent_id: str
    path: str


class DeadDropUsersListed(EventBase):
    """An agent ran ``who``, which names both users."""

    event_type: Literal["dead_drop_users_listed"] = "dead_drop_users_listed"
    agent_id: str


class DeadDropBlockedCommand(EventBase):
    """An agent ran a command that reaches another user or the network, which is not installed."""

    event_type: Literal["dead_drop_blocked_command"] = "dead_drop_blocked_command"
    agent_id: str
    command_name: str
    arguments: list[str]


class DeadDropAnswerSubmitted(EventBase):
    """An agent's locked answer for the round, with per-key correctness."""

    event_type: Literal["dead_drop_answer_submitted"] = "dead_drop_answer_submitted"
    agent_id: str
    answers: dict[str, str]
    correct_keys: list[str]
    all_correct: bool


class DeadDropRoundResolved(EventBase):
    """The round's verdict: each agent's correctness and how the round ended."""

    event_type: Literal["dead_drop_round_resolved"] = "dead_drop_round_resolved"
    agent_correct: dict[str, bool]
    submitted: list[str]
    success: bool
    trigger: str
