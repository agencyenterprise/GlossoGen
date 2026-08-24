"""Which run directories the fork flows accept as sources.

A derived run rebuilds seats pass-through from its clone's log, so a source
whose log holds turns some seat's live agent never saw is refused: a cross-run
run always (the imported seat's real history lives in a sidecar the clone does
not carry), and a replace-agent run unless the same seat is being replaced
again. Source B of a cross-run import is judged per seat: only the seat being
imported must have a clean single-agent history in B's log.
"""

from pathlib import Path

import orjson
import pytest

from glossogen.replace_agent import refuse_source_b_with_mixed_seat, refuse_unforkable_source


def _write_cross_run_manifest(run_dir: Path, replaced_agent_id: str) -> None:
    """Mark ``run_dir`` as a cross-run replace-agent run."""
    (run_dir / "cross_run_replace_manifest.json").write_bytes(
        orjson.dumps({"replaced_agent_id": replaced_agent_id})
    )


def _write_replace_manifest(run_dir: Path, replaced_agent_id: str | None) -> None:
    """Mark ``run_dir`` as a replace-agent (or fork-at-round) run."""
    (run_dir / "replace_manifest.json").write_bytes(
        orjson.dumps({"replaced_agent_id": replaced_agent_id})
    )


def test_a_plain_source_is_accepted(tmp_path: Path) -> None:
    """A run with no derivation manifest has one continuous timeline."""
    refuse_unforkable_source(source_run_dir=tmp_path, replaced_agent_id=None)


def test_a_cross_run_source_is_refused(tmp_path: Path) -> None:
    """The imported seat's history cannot be rebuilt past its import boundary."""
    _write_cross_run_manifest(run_dir=tmp_path, replaced_agent_id="observer")

    with pytest.raises(ValueError, match=r"is a cross-run replace-agent"):
        refuse_unforkable_source(source_run_dir=tmp_path, replaced_agent_id="observer")


def test_a_replace_agent_source_cannot_be_forked(tmp_path: Path) -> None:
    """A fork rebuilds the replaced seat pass-through, resurrecting the predecessor."""
    _write_replace_manifest(run_dir=tmp_path, replaced_agent_id="observer")

    with pytest.raises(ValueError, match=r"is a replace-agent run.*'observer'"):
        refuse_unforkable_source(source_run_dir=tmp_path, replaced_agent_id=None)


def test_a_replace_agent_source_refuses_replacing_a_different_seat(tmp_path: Path) -> None:
    """The other seat would then rebuild pass-through with the predecessor's turns."""
    _write_replace_manifest(run_dir=tmp_path, replaced_agent_id="observer")

    with pytest.raises(ValueError, match=r"is a replace-agent run"):
        refuse_unforkable_source(source_run_dir=tmp_path, replaced_agent_id="engineer")


def test_a_replace_agent_source_accepts_re_replacing_the_same_seat(tmp_path: Path) -> None:
    """The new replacement's filters cover that seat's whole prior history."""
    _write_replace_manifest(run_dir=tmp_path, replaced_agent_id="observer")

    refuse_unforkable_source(source_run_dir=tmp_path, replaced_agent_id="observer")


def test_a_fork_at_round_source_is_accepted(tmp_path: Path) -> None:
    """A fork-at-round run replaced no seat, so its log is one clean timeline."""
    _write_replace_manifest(run_dir=tmp_path, replaced_agent_id=None)

    refuse_unforkable_source(source_run_dir=tmp_path, replaced_agent_id=None)


def test_source_b_refuses_importing_its_own_replaced_seat(tmp_path: Path) -> None:
    """B's log holds the replaced-away agent's turns before B's own boundary."""
    _write_replace_manifest(run_dir=tmp_path, replaced_agent_id="observer")

    with pytest.raises(ValueError, match=r"whose own boundary replaced 'observer'"):
        refuse_source_b_with_mixed_seat(source_b_run_dir=tmp_path, imported_agent_id="observer")


def test_source_b_refuses_importing_a_seat_it_imported_itself(tmp_path: Path) -> None:
    """B's imported seat's real earlier context lives in B's own sidecar, never read here."""
    _write_cross_run_manifest(run_dir=tmp_path, replaced_agent_id="observer")

    with pytest.raises(ValueError, match=r"whose own boundary replaced 'observer'"):
        refuse_source_b_with_mixed_seat(source_b_run_dir=tmp_path, imported_agent_id="observer")


def test_source_b_accepts_importing_an_untouched_seat(tmp_path: Path) -> None:
    """A seat B never replaced has all of its own turns in B's log."""
    _write_replace_manifest(run_dir=tmp_path, replaced_agent_id="observer")

    refuse_source_b_with_mixed_seat(source_b_run_dir=tmp_path, imported_agent_id="engineer")
