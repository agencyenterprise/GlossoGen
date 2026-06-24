"""Data-integrity audit for the channel-noise sweep.

For every run labelled ``channel_noise`` / ``phase=baseline``, verifies:
  1. knob <-> label agreement (channel_noise_level, round_time_budget_seconds);
  2. the send_message ``message_id`` link resolves pristine -> persisted message
     for every status=="sent" result, and is None for non-sent results;
  3. each link MessageSent is a character-mask of its pristine source
     (same length, non-"_" chars identical);
  4. observed mean drop fraction on link messages ~= configured noise level;
  5. postmortem messages are uncorrupted (pristine == stored).

Also tallies cell coverage (model x noise x budget) and flags cells that do not
have exactly the expected replica count.
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, NamedTuple, cast

RUNS_ROOT = Path("runs/veyru")
EXPECTED_REPLICAS = 5
EXPECTED_NOISE = {"0.2", "0.4", "0.6"}
EXPECTED_BUDGET = {"150", "450", "800"}
EXPECTED_MODELS = {"gpt54", "opus47"}


class RunAudit(NamedTuple):
    """Per-run audit outcome."""

    run_id: str
    model: str
    noise: str
    budget: str
    knob_match: bool
    link_join_ok: bool
    nonsent_none_ok: bool
    mask_ok: bool
    pm_clean: bool
    observed_drop: float
    n_link_msgs: int
    rounds_advanced: int
    problems: tuple[str, ...]


def _label_value(labels: list[str], prefix: str) -> str | None:
    """Return the value after ``prefix`` in the first matching label."""
    for label in labels:
        if label.startswith(prefix):
            return label[len(prefix) :]
    return None


def _is_mask(pristine: str, corrupted: str) -> bool:
    """True when ``corrupted`` is ``pristine`` with a subset of chars set to '_'."""
    if len(pristine) != len(corrupted):
        return False
    return all(c == "_" or c == p for p, c in zip(pristine, corrupted))


def _audit_run(run_dir: Path) -> RunAudit | None:
    """Audit a single run dir; return None when it is not a channel_noise run."""
    labels_path = run_dir / "labels.json"
    jsonl_path = run_dir / "veyru.jsonl"
    if not labels_path.exists() or not jsonl_path.exists():
        return None
    labels = json.loads(labels_path.read_text())
    if "channel_noise" not in labels:
        return None

    noise_label = _label_value(labels=labels, prefix="noise=")
    budget_label = _label_value(labels=labels, prefix="budget=")
    model_label = _label_value(labels=labels, prefix="model=")

    events: list[dict[str, Any]] = [
        json.loads(line) for line in jsonl_path.read_text().splitlines() if line.strip()
    ]
    config: dict[str, Any] = {}
    for event in events:
        if event.get("event_type") == "simulation_started":
            raw_config = event.get("scenario_config")
            if isinstance(raw_config, dict):
                config = cast(dict[str, Any], raw_config)
            break
    knob_noise = config.get("channel_noise_level")
    knob_budget = config.get("round_time_budget_seconds")
    knob_match = (
        str(knob_noise) == str(noise_label) and str(knob_budget) == str(budget_label)
    )

    results = [
        e
        for e in events
        if e.get("event_type") == "tool_result_received" and e.get("tool_name") == "send_message"
    ]
    msgs_by_id = {
        e["message"]["message_id"]: e["message"]
        for e in events
        if e.get("event_type") == "message_sent"
    }

    problems: list[str] = []
    link_join_ok = True
    nonsent_none_ok = True
    mask_ok = True
    pm_clean = True
    link_drops: list[float] = []
    n_link = 0

    for r in results:
        raw = r["result"]
        if isinstance(raw, str):
            try:
                res = json.loads(raw)
            except json.JSONDecodeError:
                # End-of-sim race: an in-flight send rejected at session
                # teardown returns a plain error string, not a result dict.
                continue
        else:
            res = raw
        status = res.get("status")
        mid = res.get("message_id")
        pristine = r["arguments"].get("text", "")
        if status != "sent":
            if mid is not None:
                nonsent_none_ok = False
                problems.append(f"non-sent result has message_id={mid}")
            continue
        if mid is None or mid not in msgs_by_id:
            link_join_ok = False
            problems.append(f"sent result message_id={mid} did not resolve")
            continue
        message = msgs_by_id[mid]
        corrupted = message["text"]
        if message["channel_id"] == "link":
            n_link += 1
            if not _is_mask(pristine=pristine, corrupted=corrupted):
                mask_ok = False
                problems.append(f"link msg {mid} not a mask of pristine")
            elif corrupted:
                link_drops.append(sum(1 for c in corrupted if c == "_") / len(corrupted))
        else:
            if pristine != corrupted:
                pm_clean = False
                problems.append(f"postmortem msg {mid} was altered")

    observed_drop = sum(link_drops) / len(link_drops) if link_drops else 0.0
    if noise_label is not None and link_drops:
        if abs(observed_drop - float(noise_label)) > 0.08:
            problems.append(
                f"observed drop {observed_drop:.3f} far from noise={noise_label}"
            )
    rounds_advanced = sum(1 for e in events if e.get("event_type") == "round_advanced")
    if not knob_match:
        problems.append(
            f"knob mismatch: noise={knob_noise} budget={knob_budget} "
            f"vs labels noise={noise_label} budget={budget_label}"
        )

    return RunAudit(
        run_id=f"veyru/{run_dir.name}",
        model=model_label or "?",
        noise=noise_label or "?",
        budget=budget_label or "?",
        knob_match=knob_match,
        link_join_ok=link_join_ok,
        nonsent_none_ok=nonsent_none_ok,
        mask_ok=mask_ok,
        pm_clean=pm_clean,
        observed_drop=observed_drop,
        n_link_msgs=n_link,
        rounds_advanced=rounds_advanced,
        problems=tuple(problems),
    )


def main() -> None:
    """Audit every channel_noise run under RUNS_ROOT and print a report."""
    audits = [
        a for d in sorted(RUNS_ROOT.iterdir()) if d.is_dir() and (a := _audit_run(run_dir=d))
    ]
    print(f"channel_noise runs found: {len(audits)}\n")

    cells: dict[tuple[str, str, str], int] = defaultdict(int)
    for a in audits:
        cells[(a.model, a.noise, a.budget)] += 1

    print("=== cell coverage (expected 5 each) ===")
    for model in sorted(EXPECTED_MODELS):
        for noise in sorted(EXPECTED_NOISE):
            for budget in sorted(EXPECTED_BUDGET):
                n = cells.get((model, noise, budget), 0)
                flag = "" if n == EXPECTED_REPLICAS else "  <-- OFF"
                print(f"  {model:8} noise={noise} budget={budget}: {n}{flag}")

    print("\n=== per-run integrity (only rows with problems shown) ===")
    clean = 0
    for a in audits:
        all_ok = (
            a.knob_match
            and a.link_join_ok
            and a.nonsent_none_ok
            and a.mask_ok
            and a.pm_clean
            and not a.problems
        )
        if all_ok:
            clean += 1
            continue
        print(f"  {a.run_id} [{a.model} n={a.noise} b={a.budget}]")
        for p in a.problems:
            print(f"      - {p}")
    print(f"\nclean runs: {clean}/{len(audits)}")

    print("\n=== observed drop vs configured noise (mean per cell) ===")
    drop_by_cell: dict[tuple[str, str], list[float]] = defaultdict(list)
    for a in audits:
        if a.n_link_msgs:
            drop_by_cell[(a.noise, a.budget)].append(a.observed_drop)
    for (noise, budget), drops in sorted(drop_by_cell.items()):
        mean = sum(drops) / len(drops)
        print(f"  noise={noise} budget={budget}: observed mean drop={mean:.3f} (n={len(drops)})")


if __name__ == "__main__":
    main()
