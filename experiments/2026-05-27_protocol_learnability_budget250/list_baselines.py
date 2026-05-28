"""Emit one line ``<short> <model> <provider> <run_dir>`` per completed
protocol-learnability baseline run, read from each run's own event log.

A run qualifies when its labels.json carries both ``protocol_learnability`` and
``phase=baseline`` and its JSONL reached the final round (a RoundResultRecorded
for round 15 exists). The field observer's registered model/provider are read
from the AgentRegistered events so the derived runs pin the same model.
"""

import json
import sys
from pathlib import Path

SHORT_BY_MODEL = {
    "claude-sonnet-4-6": "sonnet",
    "claude-opus-4-7": "opus47",
    "gpt-5.4": "gpt54",
}


def baseline_info(run_dir: Path) -> tuple[str, str, str] | None:
    """Return ``(model, provider, short)`` for a completed baseline run, else None."""
    labels_path = run_dir / "labels.json"
    if not labels_path.exists():
        return None
    labels = json.loads(labels_path.read_text())
    if "protocol_learnability" not in labels or "phase=baseline" not in labels:
        return None
    jsonl = run_dir / "veyru.jsonl"
    if not jsonl.exists():
        return None
    model = None
    provider = None
    reached_final = False
    with jsonl.open() as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = event.get("event_type")
            if event_type == "agent_registered" and event.get("agent_id") == "field_observer":
                model = event.get("model")
                provider = event.get("provider")
            if event_type == "round_result_recorded" and event.get("round_number") == 15:
                reached_final = True
    if model is None or provider is None or not reached_final:
        return None
    model_str = str(model)
    provider_str = str(provider)
    return model_str, provider_str, SHORT_BY_MODEL.get(model_str, model_str)


def main() -> None:
    """Print ``<short> <model> <provider> <run_dir>`` for every completed baseline."""
    runs_root = Path(sys.argv[1])
    for run_dir in sorted(runs_root.glob("*")):
        if not run_dir.is_dir():
            continue
        info = baseline_info(run_dir=run_dir)
        if info is None:
            continue
        model, provider, short = info
        print(f"{short} {model} {provider} {run_dir}")


if __name__ == "__main__":
    main()
