"""Path normalization and who may touch what."""

import pytest

from glossogen.scenarios.dead_drop.server_paths import AccessPolicy, normalize_path


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("/tmp/../home/ben/x", "/home/ben/x"),
        ("//tmp///a/./b/", "/tmp/a/b"),
        ("/../..", "/"),
        ("relative/path", "/relative/path"),
    ],
)
def test_paths_normalize_before_any_rule_reads_them(raw: str, normalized: str) -> None:
    assert normalize_path(path=raw) == normalized


def test_a_private_partner_home_is_listed_but_nothing_below_it_is_reachable() -> None:
    policy = AccessPolicy(agent_id="ana", partner_id="ben", home_dirs_readable=False)
    assert policy.may_inspect(path="/home/ben")
    assert not policy.may_inspect(path="/home/ben/cases")
    assert not policy.may_read(path="/home/ben")
    assert not policy.may_read(path="/home/ben/cases/round_01.txt")


def test_a_readable_partner_home_can_be_read_and_not_written() -> None:
    policy = AccessPolicy(agent_id="ana", partner_id="ben", home_dirs_readable=True)
    assert policy.may_read(path="/home/ben/cases/round_01.txt")
    assert not policy.may_write(path="/home/ben/note.txt")


def test_writes_land_only_in_the_own_home_and_tmp() -> None:
    policy = AccessPolicy(agent_id="ana", partner_id="ben", home_dirs_readable=False)
    assert policy.may_write(path="/home/ana/notes.txt")
    assert policy.may_write(path="/tmp/drop.txt")
    assert not policy.may_write(path="/tmp")
    assert not policy.may_write(path="/home/ana")
    assert not policy.may_write(path="/etc/motd")
    assert not policy.may_write(path="/home/benjamin/x")
