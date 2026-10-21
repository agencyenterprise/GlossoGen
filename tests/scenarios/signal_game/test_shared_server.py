"""The shared server: who may see, read, change and remove what, and its replay."""

from datetime import UTC, datetime

import pytest

from glossogen.scenarios.signal_game.ids import AGENT_IDS, PLAYER_A, PLAYER_B
from glossogen.scenarios.signal_game.server_changes import ServerChange
from glossogen.scenarios.signal_game.shared_server import (
    MAX_FILE_CHARACTERS,
    MAX_NODES_PER_USER,
    NodeKind,
    PlayerNode,
    SharedServer,
    join,
)

AT = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 10, 20, 12, 5, tzinfo=UTC)


def server() -> SharedServer:
    return SharedServer(users=AGENT_IDS, at=AT)


def test_a_path_resolves_against_the_working_directory_as_a_shell_resolves_it() -> None:
    assert join(base="/home/player_a", path="notes") == "/home/player_a/notes"
    assert join(base="/home/player_a", path="x/../y") == "/home/player_a/y"
    assert join(base="/home/player_a", path="/tmp/./a") == "/tmp/a"


def test_a_new_file_is_readable_by_the_other_user_until_its_owner_closes_it() -> None:
    shared = server()
    shared.write(user=PLAYER_A, path="/home/player_a/note", content="1011", at=AT)
    assert shared.read(user=PLAYER_B, path="/home/player_a/note") == "1011"
    shared.change_mode(user=PLAYER_A, path="/home/player_a/note", mode=0o600, at=LATER)
    with pytest.raises(PermissionError):
        shared.read(user=PLAYER_B, path="/home/player_a/note")


def test_a_mode_change_moves_only_the_change_time() -> None:
    shared = server()
    shared.write(user=PLAYER_A, path="/tmp/f", content="", at=AT)
    shared.change_mode(user=PLAYER_A, path="/tmp/f", mode=0o744, at=LATER)
    info = shared.info(user=PLAYER_B, path="/tmp/f")
    assert (info.mode, info.modified, info.changed) == (0o744, AT, LATER)


def test_only_the_owner_changes_a_mode_and_setuid_is_refused() -> None:
    shared = server()
    shared.write(user=PLAYER_A, path="/tmp/f", content="", at=AT)
    with pytest.raises(PermissionError):
        shared.change_mode(user=PLAYER_B, path="/tmp/f", mode=0o777, at=AT)
    with pytest.raises(PermissionError):
        shared.change_mode(user=PLAYER_A, path="/tmp/f", mode=0o4755, at=AT)


def test_a_closed_home_hides_its_entries_but_not_its_mode() -> None:
    shared = server()
    shared.change_mode(user=PLAYER_A, path="/home/player_a", mode=0o700, at=AT)
    assert shared.look_inside(user=PLAYER_B, path="/home/player_a") == "Permission denied"
    homes = shared.list_infos(user=PLAYER_B, path="/home")
    assert [(info.name, info.mode) for info in homes] == [("player_a", 0o700), ("player_b", 0o755)]


def test_the_sticky_tmp_keeps_one_user_from_removing_the_others_file() -> None:
    shared = server()
    shared.write(user=PLAYER_A, path="/tmp/f", content="", at=AT)
    with pytest.raises(PermissionError, match="Operation not permitted"):
        shared.remove(user=PLAYER_B, path="/tmp/f", recursive=False, force=False, at=AT)


def test_limits_on_size_and_count_are_refused() -> None:
    shared = server()
    with pytest.raises(OSError, match="File too large"):
        shared.write(user=PLAYER_A, path="/tmp/f", content="x" * (MAX_FILE_CHARACTERS + 1), at=AT)
    for index in range(MAX_NODES_PER_USER):
        shared.write(user=PLAYER_A, path=f"/tmp/{index}", content="", at=AT)
    with pytest.raises(OSError, match="Disk quota exceeded"):
        shared.write(user=PLAYER_A, path="/tmp/one-more", content="", at=AT)


def test_a_directory_is_copied_parents_first_and_moved_whole() -> None:
    shared = server()
    shared.make_directory(user=PLAYER_A, path="/tmp/a/b", parents=True, at=AT)
    shared.write(user=PLAYER_A, path="/tmp/a/b/f", content="1", at=AT)
    shared.copy(user=PLAYER_B, source="/tmp/a", destination="/tmp/c", recursive=True, at=AT)
    assert shared.read(user=PLAYER_B, path="/tmp/c/b/f") == "1"
    assert shared.info(user=PLAYER_B, path="/tmp/c/b").owner == PLAYER_B
    shared.move(user=PLAYER_B, source="/tmp/c", destination="/tmp/d", at=AT)
    assert shared.kind_of(user=PLAYER_B, path="/tmp/d/b/f") is NodeKind.FILE
    assert not shared.exists(user=PLAYER_B, path="/tmp/c")


def test_replaying_the_changes_rebuilds_the_same_server() -> None:
    shared = server()
    changes: list[ServerChange] = []
    changes += shared.make_directory(user=PLAYER_A, path="/tmp/d", parents=False, at=AT)
    changes += shared.write(user=PLAYER_A, path="/tmp/d/f", content="1011", at=AT)
    changes += shared.change_mode(user=PLAYER_A, path="/tmp/d/f", mode=0o600, at=LATER)
    changes += shared.move(user=PLAYER_A, source="/tmp/d", destination="/tmp/e", at=LATER)
    rebuilt = server()
    for change in changes:
        rebuilt.apply(change=change, at=LATER)
    assert (
        rebuilt.player_nodes()
        == shared.player_nodes()
        == [
            PlayerNode(path="/tmp/e", kind=NodeKind.DIRECTORY, owner=PLAYER_A, content=""),
            PlayerNode(path="/tmp/e/f", kind=NodeKind.FILE, owner=PLAYER_A, content="1011"),
        ]
    )
    assert rebuilt.info(user=PLAYER_A, path="/tmp/e/f").mode == 0o600
