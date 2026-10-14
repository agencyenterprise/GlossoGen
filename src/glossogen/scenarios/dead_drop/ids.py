"""Identifiers shared across the dead_drop scenario: agents, paths, tools, triggers, modes."""

from enum import StrEnum

ANA_ID = "ana"
BEN_ID = "ben"
AGENT_IDS: tuple[str, str] = (ANA_ID, BEN_ID)
PARTNER_OF: dict[str, str] = {ANA_ID: BEN_ID, BEN_ID: ANA_ID}

HOSTNAME = "lab"

HOME_ROOT = "/home"
TMP_PATH = "/tmp"
CASES_DIRNAME = "cases"
PASSWD_PATH = "/etc/passwd"

FIRST_USER_ID = 1001
ROOT_USER = "root"
ROOT_USER_ID = 0

SYSTEM_AUTHOR = ROOT_USER
"""The author recorded for files the scenario writes, such as case files."""

RUN_COMMAND_TOOL = "run_command"
SUBMIT_ANSWER_TOOL = "submit_answer"
SEND_MESSAGE_TOOL = "send_message"
HIDDEN_CHANNEL_TOOLS: frozenset[str] = frozenset(
    {"read_channel", "list_channels", "get_channel_members"}
)

LINK_CHANNEL_ID = "link"

BOTH_SUBMITTED_TRIGGER = "both_submitted"

SYSTEM_TEMPLATE = "analyst_system.jinja"
INJECTION_TEMPLATE = "analyst_injection.jinja"
CASE_FILE_TEMPLATE = "case_file.jinja"
RELEASE_NOTICE_TEMPLATE = "release_notice.jinja"
PROTOCOL_SUFFIX_TEMPLATE = "protocol_suffix.jinja"
PROTOCOL_INITIAL_TEMPLATE = "protocol_initial.jinja"
PROTOCOL_CONTINUE_TEMPLATE = "protocol_continue.jinja"
DESCRIPTION_TEMPLATE = "description.jinja"


class Disclosure(StrEnum):
    """How much an agent is told about its partner, least first.

    Only ``fs_instructed`` changes the system prompt, naming the partner and
    ``/tmp``. Below it the levels differ in the round briefings from round 2:
    ``none`` reports the agent's own result, ``partner_known`` also the result of
    "the other analyst", and ``fs_shared_known`` the partner's result under its
    username.
    """

    NONE = "none"
    PARTNER_KNOWN = "partner_known"
    FS_SHARED_KNOWN = "fs_shared_known"
    FS_INSTRUCTED = "fs_instructed"


class ChannelMode(StrEnum):
    """Whether the two agents also share a chat channel."""

    NONE = "none"
    CHAT = "chat"


class FsOperation(StrEnum):
    """A change an agent made to the filesystem, as logged and replayed."""

    WRITE = "write"
    APPEND = "append"
    MKDIR = "mkdir"
    REMOVE = "remove"
    COPY = "copy"
    MOVE = "move"
    TOUCH = "touch"


def home_of(agent_id: str) -> str:
    """The home directory of ``agent_id``."""
    return f"{HOME_ROOT}/{agent_id}"


def user_id_of(agent_id: str) -> int:
    """The numeric user id of ``agent_id``, as ``/etc/passwd`` and ``id`` show it."""
    return FIRST_USER_ID + AGENT_IDS.index(agent_id)


def user_id_by_name(name: str) -> int | None:
    """The numeric id of the user ``/etc/passwd`` lists as ``name``, or None for no such user."""
    if name == ROOT_USER:
        return ROOT_USER_ID
    if name in AGENT_IDS:
        return user_id_of(agent_id=name)
    return None


def case_file_path(agent_id: str, round_number: int) -> str:
    """Where round ``round_number``'s case file for ``agent_id`` is written."""
    return f"{home_of(agent_id=agent_id)}/{CASES_DIRNAME}/round_{round_number:02d}.txt"
