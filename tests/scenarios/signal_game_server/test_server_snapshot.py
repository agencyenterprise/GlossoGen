"""Snapshots of the shared server: tar round trip, diffs into changes, replay, quotas."""

import io
import tarfile
from datetime import UTC, datetime

from glossogen.scenarios.signal_game.ids import AGENT_IDS, PLAYER_A, PLAYER_B
from glossogen.scenarios.signal_game_server.server_changes import ServerChange, ServerChangeKind
from glossogen.scenarios.signal_game_server.server_snapshot import (
    MAX_FILE_CHARACTERS,
    MAX_NODES_PER_USER,
    NodeKind,
    ServerSnapshot,
    SnapshotNode,
    apply_change,
    diff_snapshots,
    empty_snapshot,
    parse_tar,
    to_tar,
)

AT = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 10, 20, 12, 5, tzinfo=UTC)


def node(kind: NodeKind, owner: str, mode: int, content: str) -> SnapshotNode:
    return SnapshotNode(
        kind=kind, owner=owner, mode=mode, modified=AT, content=content.encode("utf-8")
    )


def with_nodes(extra: dict[str, SnapshotNode]) -> ServerSnapshot:
    snapshot = empty_snapshot(users=AGENT_IDS, at=AT)
    snapshot.nodes.update(extra)
    return snapshot


def test_a_snapshot_survives_the_tar_round_trip() -> None:
    before = with_nodes(
        {
            "/tmp/d": node(kind=NodeKind.DIRECTORY, owner=PLAYER_A, mode=0o700, content=""),
            "/tmp/d/f": node(kind=NodeKind.FILE, owner=PLAYER_A, mode=0o640, content="1011\n"),
            "/home/player_b/x": node(kind=NodeKind.FILE, owner=PLAYER_B, mode=0o644, content=""),
        }
    )
    after = parse_tar(data=to_tar(snapshot=before), users=AGENT_IDS)
    assert after.nodes == before.nodes


def test_a_diff_reports_creations_edits_mode_changes_and_removals() -> None:
    before = with_nodes(
        {
            "/tmp/keep": node(kind=NodeKind.FILE, owner=PLAYER_A, mode=0o644, content="a"),
            "/tmp/gone": node(kind=NodeKind.DIRECTORY, owner=PLAYER_B, mode=0o755, content=""),
            "/tmp/gone/f": node(kind=NodeKind.FILE, owner=PLAYER_B, mode=0o644, content="b"),
        }
    )
    after = with_nodes(
        {
            "/tmp/keep": node(kind=NodeKind.FILE, owner=PLAYER_A, mode=0o600, content="aa"),
            "/tmp/new": node(kind=NodeKind.DIRECTORY, owner=PLAYER_B, mode=0o755, content=""),
            "/tmp/new/g": node(kind=NodeKind.FILE, owner=PLAYER_B, mode=0o600, content="c"),
        }
    )
    changes = diff_snapshots(before=before, after=after)
    assert [(change.kind, change.actor, change.path) for change in changes] == [
        (ServerChangeKind.REMOVE, PLAYER_B, "/tmp/gone"),
        (ServerChangeKind.WRITE, PLAYER_A, "/tmp/keep"),
        (ServerChangeKind.CHMOD, PLAYER_A, "/tmp/keep"),
        (ServerChangeKind.MKDIR, PLAYER_B, "/tmp/new"),
        (ServerChangeKind.WRITE, PLAYER_B, "/tmp/new/g"),
    ]
    assert changes[1].content == "aa"
    assert changes[2].mode == 0o600
    assert changes[4].mode == 0o600


def test_a_touch_alone_is_a_touch_and_an_unchanged_server_is_no_change() -> None:
    before = with_nodes(
        {"/tmp/f": node(kind=NodeKind.FILE, owner=PLAYER_A, mode=0o644, content="x")}
    )
    assert diff_snapshots(before=before, after=before) == []
    after = with_nodes(
        {"/tmp/f": node(kind=NodeKind.FILE, owner=PLAYER_A, mode=0o644, content="x")}
    )
    after.nodes["/tmp/f"] = after.nodes["/tmp/f"]._replace(modified=LATER)
    [change] = diff_snapshots(before=before, after=after)
    assert (change.kind, change.modified) == (ServerChangeKind.TOUCH, LATER)


def test_replaying_a_diff_rebuilds_the_same_snapshot() -> None:
    before = empty_snapshot(users=AGENT_IDS, at=AT)
    after = with_nodes(
        {
            "/home/player_a/d": node(
                kind=NodeKind.DIRECTORY, owner=PLAYER_A, mode=0o700, content=""
            ),
            "/home/player_a/d/f": node(
                kind=NodeKind.FILE, owner=PLAYER_A, mode=0o600, content="1011"
            ),
            "/tmp/z": node(kind=NodeKind.FILE, owner=PLAYER_B, mode=0o644, content=""),
        }
    )
    after.nodes["/home/player_a"] = after.nodes["/home/player_a"]._replace(mode=0o711)
    rebuilt = empty_snapshot(users=AGENT_IDS, at=AT)
    for change in diff_snapshots(before=before, after=after):
        apply_change(snapshot=rebuilt, change=change, at=AT)
    assert rebuilt.nodes == after.nodes


BINARY = bytes([0x42, 0x4D, 0x00, 0xFF, 0x00, 0xFF, 0x80, 0xC3])
"""Bytes that are not valid UTF-8, as the pixel data of an image file holds."""


def test_binary_content_survives_the_tar_round_trip() -> None:
    before = with_nodes(
        {
            "/tmp/b.bmp": SnapshotNode(
                kind=NodeKind.FILE, owner=PLAYER_A, mode=0o644, modified=AT, content=BINARY
            )
        }
    )
    after = parse_tar(data=to_tar(snapshot=before), users=AGENT_IDS)
    assert after.nodes["/tmp/b.bmp"].content == BINARY


def test_replaying_a_binary_write_restores_its_bytes() -> None:
    after = with_nodes(
        {
            "/tmp/b.bmp": SnapshotNode(
                kind=NodeKind.FILE, owner=PLAYER_A, mode=0o644, modified=AT, content=BINARY
            )
        }
    )
    [change] = diff_snapshots(before=empty_snapshot(users=AGENT_IDS, at=AT), after=after)
    assert change.content is not None and "\ufffd" in change.content
    logged = ServerChange.model_validate_json(change.model_dump_json())
    rebuilt = empty_snapshot(users=AGENT_IDS, at=AT)
    apply_change(snapshot=rebuilt, change=logged, at=AT)
    assert rebuilt.nodes["/tmp/b.bmp"].content == BINARY


def test_a_text_write_carries_no_base64() -> None:
    after = with_nodes(
        {"/tmp/f": node(kind=NodeKind.FILE, owner=PLAYER_A, mode=0o644, content="1011")}
    )
    [change] = diff_snapshots(before=empty_snapshot(users=AGENT_IDS, at=AT), after=after)
    assert (change.content, change.content_base64) == ("1011", None)


def test_quotas_are_checked_per_owner_and_per_file() -> None:
    clean = empty_snapshot(users=AGENT_IDS, at=AT)
    assert clean.quota_breach() is None
    many = with_nodes(
        {
            f"/tmp/{index}": node(kind=NodeKind.FILE, owner=PLAYER_A, mode=0o644, content="")
            for index in range(MAX_NODES_PER_USER + 1)
        }
    )
    breach = many.quota_breach()
    assert breach is not None
    assert breach.user == PLAYER_A
    big = with_nodes(
        {
            "/tmp/big": node(
                kind=NodeKind.FILE,
                owner=PLAYER_B,
                mode=0o644,
                content="x" * (MAX_FILE_CHARACTERS + 1),
            )
        }
    )
    breach = big.quota_breach()
    assert breach is not None
    assert (breach.user, "/tmp/big" in breach.reason) == (PLAYER_B, True)


def test_the_tree_lists_roots_and_nodes_with_owner_and_mode() -> None:
    snapshot = with_nodes(
        {"/tmp/f": node(kind=NodeKind.FILE, owner=PLAYER_A, mode=0o600, content="")}
    )
    assert snapshot.tree_lines() == [
        "/home/player_a directory player_a 0755",
        "/home/player_b directory player_b 0755",
        "/tmp directory root 1777",
        "/tmp/f file player_a 0600",
    ]


def test_names_with_dots_survive_the_tar_round_trip() -> None:
    before = with_nodes(
        {
            "/tmp/x.": node(kind=NodeKind.FILE, owner=PLAYER_A, mode=0o644, content="1"),
            "/tmp/.d": node(kind=NodeKind.DIRECTORY, owner=PLAYER_A, mode=0o755, content=""),
            "/home/player_b/notes...": node(
                kind=NodeKind.FILE, owner=PLAYER_B, mode=0o644, content=""
            ),
        }
    )
    after = parse_tar(data=to_tar(snapshot=before), users=AGENT_IDS)
    assert set(after.nodes) == set(before.nodes)


def test_a_special_file_in_the_tar_is_a_quota_breach() -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:") as archive:
        fifo = tarfile.TarInfo(name="tmp/p")
        fifo.type = tarfile.FIFOTYPE
        fifo.uname = PLAYER_A
        fifo.uid = 1001
        archive.addfile(fifo)
    snapshot = parse_tar(data=buffer.getvalue(), users=AGENT_IDS)
    assert snapshot.nodes == {}
    breach = snapshot.quota_breach()
    assert breach is not None
    assert (breach.user, "/tmp/p" in breach.reason) == (PLAYER_A, True)
