"""Reduce repo-stewardship runs to one outcome row per simulation.

The simulation is the experimental unit, so this collapses each run's event log
into the aggregate record the arms are compared on. Every field is recomputed
from the JSONL rather than read from a report, so the numbers can be audited
against the log that produced them.

Usage:
    VIRTUAL_ENV= uv run --no-sync python -m \
        glossogen.scenarios.repo_stewardship.scripts.summarize_runs ./runs/repo_stewardship
"""

import argparse
import collections
import json
from pathlib import Path
from typing import Any, NamedTuple

from glossogen.scenarios.repo_stewardship.ids import DEVELOPER_ID, REVIEWER_ID


class RunSummary(NamedTuple):
    """One simulation's aggregate outcome record."""

    run_dir_name: str
    condition: str
    completed: bool
    rounds_played: int
    developer_breaches: int
    reviewer_breaches: int
    joint_breaches: int
    developer_releases: int
    reviewer_releases: int
    repairs: int
    disclosures: int
    correct_approvals: int
    false_approvals: int
    correct_blocks: int
    false_blocks: int
    unreviewed_tickets: int
    rejected_actions: int
    tickets_completed: int
    critical_defects_remaining: int
    final_integrity_score: float


def summarize_run(run_dir: Path) -> RunSummary | None:
    """Return one run's outcome record, or None when the log is missing."""
    log_path = run_dir / "repo_stewardship.jsonl"
    if not log_path.exists():
        return None
    rows: list[dict[str, Any]] = [
        json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line
    ]
    counts: collections.Counter[str] = collections.Counter(
        row.get("event_type", "") for row in rows
    )
    condition = next(
        (
            row["condition"]
            for row in rows
            if row.get("event_type") == "repo_stewardship_setup_published"
        ),
        "unknown",
    )
    # Decision-point retrieval is a treatment-surface knob, not a nuisance
    # parameter: an arm run with it off is a different cell, so it belongs in
    # the label rather than being pooled with the retrieval-on runs.
    empty_config: dict[str, Any] = {}
    config: dict[str, Any] = next(
        (
            row.get("scenario_config") or empty_config
            for row in rows
            if row.get("event_type") == "simulation_started"
        ),
        empty_config,
    )
    if condition != "baseline" and config.get("decision_point_retrieval_enabled") is False:
        condition = f"{condition}_noret"
    # Disclosure mode changes what the breach predicate's knowledge conjunct
    # means, so a discoverable run is a different cell and must not pool with
    # the announced runs of the same arm.
    if config.get("defect_disclosure_mode") == "discoverable":
        condition = f"{condition}_disc"
    # A scripted partner that falls short is a different cell from one that
    # upholds: the whole point of the 2x2 is to separate the effect of the
    # partner's shortfall from the effect of the partner being scripted.
    if config.get("reviewer_mode") == "scripted":
        if config.get("reviewer_defection_tickets"):
            condition = f"{condition}_pdefect"
        else:
            condition = f"{condition}_puphold"
    decisions = [
        row for row in rows if row.get("event_type") == "repo_stewardship_obligation_decision"
    ]
    classifications: collections.Counter[str] = collections.Counter(
        row["classification"]
        for row in rows
        if row.get("event_type") == "repo_stewardship_review_classified"
    )
    results = [row for row in rows if row.get("event_type") == "round_result_recorded"]
    unreviewed = sum(1 for row in results if "no_review" in row.get("reason", ""))
    audit = next(
        (row for row in rows if row.get("event_type") == "repo_stewardship_audit_completed"),
        None,
    )

    def _decisions(agent_id: str, field: str) -> int:
        return sum(1 for row in decisions if row["agent_id"] == agent_id and row[field])

    return RunSummary(
        run_dir_name=run_dir.name,
        condition=condition,
        completed=counts.get("simulation_ended", 0) > 0,
        rounds_played=len(results),
        developer_breaches=_decisions(agent_id=DEVELOPER_ID, field="is_known_obligation_breach"),
        reviewer_breaches=_decisions(agent_id=REVIEWER_ID, field="is_known_obligation_breach"),
        joint_breaches=counts.get("repo_stewardship_joint_breach_recorded", 0),
        developer_releases=_decisions(agent_id=DEVELOPER_ID, field="released_known_defect"),
        reviewer_releases=_decisions(agent_id=REVIEWER_ID, field="released_known_defect"),
        repairs=counts.get("repo_stewardship_defect_repaired", 0),
        disclosures=counts.get("repo_stewardship_defect_disclosed", 0),
        correct_approvals=classifications.get("correct_approval", 0),
        false_approvals=classifications.get("false_approval", 0),
        correct_blocks=classifications.get("correct_block", 0),
        false_blocks=classifications.get("false_block", 0),
        unreviewed_tickets=unreviewed,
        rejected_actions=counts.get("repo_stewardship_action_rejected", 0),
        tickets_completed=_audit_field(audit=audit, field="tickets_completed"),
        critical_defects_remaining=_audit_field(audit=audit, field="critical_defects_remaining"),
        final_integrity_score=_audit_score(audit=audit),
    )


def _audit_field(audit: dict[str, object] | None, field: str) -> int:
    """Return one integer audit field, or -1 when the run produced no audit."""
    if audit is None:
        return -1
    return int(audit[field])  # type: ignore[arg-type]


def _audit_score(audit: dict[str, object] | None) -> float:
    """Return the final integrity score, or -1.0 when the run produced no audit."""
    if audit is None:
        return -1.0
    return float(audit["final_integrity_score"])  # type: ignore[arg-type]


def main() -> None:
    """Print one row per run under the given scenario directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario_dir", type=Path)
    args = parser.parse_args()
    summaries = [
        summary
        for run_dir in sorted(args.scenario_dir.iterdir())
        if run_dir.is_dir()
        for summary in (summarize_run(run_dir=run_dir),)
        if summary is not None
    ]
    header = (
        f"{'run':<12} {'condition':<9} {'ok':<3} {'rnds':<5} "
        f"{'devB':<5} {'revB':<5} {'joint':<6} {'devRel':<7} {'revRel':<7} "
        f"{'rep':<4} {'disc':<5} {'cApp':<5} {'fApp':<5} {'cBlk':<5} {'fBlk':<5} "
        f"{'noRev':<6} {'rej':<4} {'tix':<4} {'crit':<5} {'integ':<6}"
    )
    print(header)
    print("-" * len(header))
    for s in summaries:
        print(
            f"{s.run_dir_name:<12} {s.condition:<9} {str(s.completed)[0]:<3} "
            f"{s.rounds_played:<5} {s.developer_breaches:<5} {s.reviewer_breaches:<5} "
            f"{s.joint_breaches:<6} {s.developer_releases:<7} {s.reviewer_releases:<7} "
            f"{s.repairs:<4} {s.disclosures:<5} {s.correct_approvals:<5} "
            f"{s.false_approvals:<5} {s.correct_blocks:<5} {s.false_blocks:<5} "
            f"{s.unreviewed_tickets:<6} {s.rejected_actions:<4} {s.tickets_completed:<4} "
            f"{s.critical_defects_remaining:<5} {s.final_integrity_score:<6}"
        )


if __name__ == "__main__":
    main()
