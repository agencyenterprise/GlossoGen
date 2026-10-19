"""Authorship follows content through writes, appends, copies, moves and removals."""

from glossogen.scenarios.dead_drop.authorship import AuthorshipLedger, Location
from glossogen.scenarios.dead_drop.ids import SYSTEM_AUTHOR


def at(path: str) -> Location:
    return Location(volume="tmp", path=path)


def test_a_write_makes_the_writer_the_only_author() -> None:
    ledger = AuthorshipLedger()
    ledger.record_write(location=at(path="/tmp/x"), author="ana")
    ledger.record_write(location=at(path="/tmp/x"), author="ben")
    assert ledger.authors_of(location=at(path="/tmp/x")) == ["ben"]


def test_an_append_keeps_the_earlier_author() -> None:
    ledger = AuthorshipLedger()
    ledger.record_write(location=at(path="/tmp/x"), author="ana")
    ledger.record_append(location=at(path="/tmp/x"), author="ben")
    assert ledger.authors_of(location=at(path="/tmp/x")) == ["ana", "ben"]


def test_a_copy_carries_the_authors_of_a_whole_directory() -> None:
    ledger = AuthorshipLedger()
    ledger.record_write(location=at(path="/tmp/box/a"), author="ana")
    ledger.record_copy(
        source=at(path="/tmp/box"),
        destination=Location(volume="server", path="/home/ben/box"),
        actor="ben",
    )
    assert ledger.authors_of(location=Location(volume="server", path="/home/ben/box/a")) == ["ana"]
    assert ledger.authors_of(location=at(path="/tmp/box/a")) == ["ana"]


def test_a_move_leaves_nothing_at_the_source() -> None:
    ledger = AuthorshipLedger()
    ledger.record_write(location=at(path="/tmp/a"), author="ana")
    ledger.record_move(source=at(path="/tmp/a"), destination=at(path="/tmp/b"), actor="ben")
    assert ledger.authors_of(location=at(path="/tmp/a")) == []
    assert ledger.authors_of(location=at(path="/tmp/b")) == ["ana"]


def test_a_move_onto_itself_changes_nothing() -> None:
    ledger = AuthorshipLedger()
    ledger.record_write(location=at(path="/tmp/a"), author="ana")
    ledger.record_move(source=at(path="/tmp/a"), destination=at(path="/tmp/a"), actor="ana")
    assert ledger.authors_of(location=at(path="/tmp/a")) == ["ana"]


def test_a_copy_of_the_scenarios_file_becomes_the_copiers() -> None:
    """Copying a case file to /tmp publishes it as the agent's, as ``cat > /tmp/x`` would."""
    ledger = AuthorshipLedger()
    case_file = Location(volume="server", path="/home/ana/cases/round_01.txt")
    ledger.record_write(location=case_file, author=SYSTEM_AUTHOR)
    ledger.record_copy(source=case_file, destination=at(path="/tmp/ana.txt"), actor="ana")
    ledger.record_move(source=at(path="/tmp/ana.txt"), destination=at(path="/tmp/a"), actor="ben")
    assert ledger.authors_of(location=at(path="/tmp/a")) == ["ana"]
    assert ledger.authors_of(location=case_file) == [SYSTEM_AUTHOR]


def test_removing_a_directory_forgets_everything_below_it_and_only_that() -> None:
    ledger = AuthorshipLedger()
    ledger.record_write(location=at(path="/tmp/box/a"), author="ana")
    ledger.record_write(location=at(path="/tmp/boxes"), author="ana")
    ledger.record_remove(location=at(path="/tmp/box"))
    assert ledger.authors_of(location=at(path="/tmp/box/a")) == []
    assert ledger.authors_of(location=at(path="/tmp/boxes")) == ["ana"]
