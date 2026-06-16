"""Align protocol-learnability derived `src=` labels with the authoritative manifest, then
flag the runs that must be archived, so the idempotent launchers re-run exactly the deficit.

Two invariants for the spreadsheet cohort (`runs/veyru`, label `protocol_learnability`):
1. no derived run's manifest `source_run_id` may point to a superseded/archived run;
2. every run must have run the easy cases (`easy_round_numbers=[1,2,3,6,13]`).

For every derived run whose `src=` label disagrees with its `replace_manifest.json`
`source_run_id` (the truth), this does one of:

- **relabel** — if the manifest source is a *current, non-superseded* baseline: rewrite the
  `src=` label to the manifest source. These runs are sound (correct easy cases, correct
  clone source); only the label drifted. After this the launchers count them and won't
  duplicate them.
- **drop** — if the manifest source is *superseded* (so the run violates invariant 1 and its
  true source is untrustworthy): remove the `protocol_learnability` label so it leaves the
  cohort (its data is preserved, like the earlier stale-run de-labeling).

Dry-run by default; pass ``--apply`` to write. Never touches baselines or any non-``src=``
label, and only ever removes ``protocol_learnability`` (never eval/other labels).
"""

import argparse
import csv
import json
import pathlib

RUNS = pathlib.Path("runs")
COHORT = "protocol_learnability"


def _one_step() -> dict[str, str]:
    out: dict[str, str] = {}
    path = RUNS / "supersedes_map.csv"
    if path.exists():
        with path.open() as h:
            for row in csv.DictReader(h):
                if row.get("old_run_id") and row.get("new_run_id"):
                    out[row["old_run_id"]] = row["new_run_id"]
    return out


def _superseded_set(one_step: dict[str, str]) -> set[str]:
    superseded = set(one_step.keys())
    archived = RUNS / "_superseded" / "veyru"
    if archived.exists():
        for d in archived.iterdir():
            if d.is_dir():
                superseded.add(f"veyru/{d.name}")
    return superseded


def _labels(run_dir: pathlib.Path) -> list[str]:
    path = run_dir / "labels.json"
    return json.loads(path.read_text()) if path.exists() else []


def _label_value(labels: list[str], prefix: str) -> str | None:
    return next((x[len(prefix) :] for x in labels if x.startswith(prefix)), None)


def _manifest_source(run_dir: pathlib.Path) -> str | None:
    for name in ("replace_manifest.json", "cross_run_replace_manifest.json"):
        path = run_dir / name
        if path.exists():
            payload = json.loads(path.read_text())
            return payload.get("source_run_id") or payload.get("source_a_run_id")
    return None


def _current_baselines() -> set[str]:
    out: set[str] = set()
    for d in (RUNS / "veyru").iterdir():
        if not d.is_dir():
            continue
        labels = _labels(run_dir=d)
        if COHORT in labels and "phase=baseline" in labels:
            out.add(f"veyru/{d.name}")
    return out


def main() -> None:
    """Plan (and optionally apply) the relabel/drop actions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    superseded = _superseded_set(one_step=_one_step())
    baselines = _current_baselines()
    relabel: list[tuple[str, str, str]] = []
    drop: list[str] = []

    for d in sorted((RUNS / "veyru").iterdir()):
        if not d.is_dir():
            continue
        labels = _labels(run_dir=d)
        if COHORT not in labels:
            continue
        phase = _label_value(labels=labels, prefix="phase=")
        if phase is None or phase == "baseline":
            continue
        rid = f"veyru/{d.name}"
        src_label = _label_value(labels=labels, prefix="src=")
        manifest = _manifest_source(run_dir=d)
        if manifest is None or src_label == manifest:
            continue
        if manifest in baselines and manifest not in superseded:
            relabel.append((rid, src_label or "", manifest))
        else:
            drop.append(rid)

    print(f"RELABEL src= -> manifest source ({len(relabel)} runs):")
    for rid, old, new in relabel:
        print(f"  {rid}: src={old} -> src={new}")
    print(f"\nDROP protocol_learnability ({len(drop)} runs, manifest source superseded):")
    for rid in drop:
        print(f"  {rid}")

    if not args.apply:
        print("\n(dry-run — pass --apply to write)")
        return

    for rid, _, new in relabel:
        path = RUNS / rid.split("/")[0] / rid.split("/")[1] / "labels.json"
        labels = json.loads(path.read_text())
        labels = [x for x in labels if not x.startswith("src=")] + [f"src={new}"]
        path.write_text(json.dumps(labels, indent=2))
    for rid in drop:
        path = RUNS / rid.split("/")[0] / rid.split("/")[1] / "labels.json"
        labels = [x for x in json.loads(path.read_text()) if x != COHORT]
        path.write_text(json.dumps(labels, indent=2))
    print(f"\nAPPLIED: relabelled {len(relabel)}, dropped {len(drop)}.")


if __name__ == "__main__":
    main()
