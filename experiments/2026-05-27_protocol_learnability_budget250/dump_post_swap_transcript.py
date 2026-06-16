"""Post-swap evidence extractor for protocol-learnability replace runs.

For a single veyru run directory, reconstructs — per round in a chosen window
(default the post-swap rounds 16-25) — the case, the correct procedure the judge
scored against, the verbatim ``link`` channel exchange, the field observer's
``stabilize_veyru`` action(s), and the per-attempt judge verdict. This is the
raw evidence used to reason about whether a swapped-in field observer learned
the team's compressed protocol and applied it correctly.

The event log stores the ``message`` payload either as a JSON-decoded dict or as
a Python ``repr`` string (depending on writer path), so both shapes are parsed.
"""

import argparse
import ast
import json
import re
from pathlib import Path
from typing import NamedTuple, cast

_CHAN_RE = re.compile(r"'channel_id': '(?P<c>[^']+)'")
_SENDER_RE = re.compile(r"'sender_agent_id': '(?P<s>[^']+)'")
_TEXT_RE = re.compile(r"'text': (?P<q>['\"])(?P<t>.*?)(?P=q), 'timestamp':", re.DOTALL)


class LinkMessage(NamedTuple):
    """One message on the budget-constrained comm link."""

    sender: str
    text: str


class StabilizeAttempt(NamedTuple):
    """One ``stabilize_veyru`` call by the field observer and its judge verdict."""

    action: str
    expected: str
    judge_match: bool
    judge_explanation: str


class RoundEvidence(NamedTuple):
    """All post-swap evidence for one round."""

    round_number: int
    failure_name: str
    stellar_reading: str
    round_success: bool
    round_reason: str
    link_messages: list[LinkMessage]
    attempts: list[StabilizeAttempt]


def _parse_message(payload: dict[str, object] | str) -> tuple[str, str, str]:
    """Return ``(channel_id, sender, text)`` from a dict or repr-string payload."""
    if isinstance(payload, dict):
        return (
            str(payload.get("channel_id", "")),
            str(payload.get("sender_agent_id", "")),
            str(payload.get("text", "")),
        )
    chan_match = _CHAN_RE.search(payload)
    sender_match = _SENDER_RE.search(payload)
    text_match = _TEXT_RE.search(payload)
    channel = ""
    if chan_match is not None:
        channel = chan_match.group("c")
    sender = ""
    if sender_match is not None:
        sender = sender_match.group("s")
    body = ""
    if text_match is not None:
        body = text_match.group("t")
    return channel, sender, body


def _load_events(run_dir: Path) -> list[dict[str, object]]:
    """Read every JSONL event line for the run."""
    events: list[dict[str, object]] = []
    jsonl_path = run_dir / "veyru.jsonl"
    with jsonl_path.open() as handle:
        for line in handle:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _parse_stabilize_action(arguments: object) -> str:
    """Extract the ``action`` argument from a ``stabilize_veyru`` tool call."""
    if isinstance(arguments, dict):
        return str(cast(dict[str, object], arguments).get("action", ""))
    text = str(arguments)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return text
    if isinstance(parsed, dict):
        return str(cast(dict[str, object], parsed).get("action", text))
    return text


def extract_round_evidence(run_dir: Path, round_lo: int, round_hi: int) -> list[RoundEvidence]:
    """Build per-round evidence for ``round_lo..round_hi`` inclusive."""
    events = _load_events(run_dir=run_dir)
    failure_by_round: dict[int, str] = {}
    stellar_by_round: dict[int, str] = {}
    links_by_round: dict[int, list[LinkMessage]] = {}
    actions_by_round: dict[int, list[str]] = {}
    verdicts_by_round: dict[int, list[tuple[str, bool, str]]] = {}
    success_by_round: dict[int, bool] = {}
    reason_by_round: dict[int, str] = {}

    for event in events:
        round_number = int(str(event.get("round_number", 0)))
        if round_number < round_lo or round_number > round_hi:
            continue
        event_type = event.get("event_type")
        if event_type == "veyru_case_started":
            failure_by_round[round_number] = str(event.get("failure_name", "?"))
            stellar_by_round[round_number] = str(event.get("stellar_reading", ""))
        elif event_type == "message_sent":
            payload = event["message"]
            if isinstance(payload, dict):
                channel, sender, text = _parse_message(payload=cast(dict[str, object], payload))
            else:
                channel, sender, text = _parse_message(payload=str(payload))
            if channel == "link":
                links_by_round.setdefault(round_number, []).append(
                    LinkMessage(sender=sender, text=text)
                )
        elif event_type == "tool_call_invoked":
            if event.get("tool_name") == "stabilize_veyru":
                actions_by_round.setdefault(round_number, []).append(
                    _parse_stabilize_action(arguments=event.get("arguments", "{}"))
                )
        elif event_type == "veyru_stabilization_judged":
            verdicts_by_round.setdefault(round_number, []).append(
                (
                    str(event.get("expected_actions", "")),
                    event.get("judge_match") in (True, "True"),
                    str(event.get("judge_explanation", "")),
                )
            )
        elif event_type == "round_result_recorded":
            success_by_round[round_number] = event.get("success") in (True, "True")
            reason_by_round[round_number] = str(event.get("reason", ""))

    rounds: list[RoundEvidence] = []
    for round_number in range(round_lo, round_hi + 1):
        actions = actions_by_round.get(round_number, [])
        verdicts = verdicts_by_round.get(round_number, [])
        attempts: list[StabilizeAttempt] = []
        for index, verdict in enumerate(verdicts):
            expected, match, explanation = verdict
            action = ""
            if index < len(actions):
                action = actions[index]
            attempts.append(
                StabilizeAttempt(
                    action=action,
                    expected=expected,
                    judge_match=match,
                    judge_explanation=explanation,
                )
            )
        rounds.append(
            RoundEvidence(
                round_number=round_number,
                failure_name=failure_by_round.get(round_number, "?"),
                stellar_reading=stellar_by_round.get(round_number, ""),
                round_success=success_by_round.get(round_number, False),
                round_reason=reason_by_round.get(round_number, ""),
                link_messages=links_by_round.get(round_number, []),
                attempts=attempts,
            )
        )
    return rounds


def render(run_dir: Path, round_lo: int, round_hi: int) -> str:
    """Render a human-readable per-round evidence report."""
    rounds = extract_round_evidence(run_dir=run_dir, round_lo=round_lo, round_hi=round_hi)
    n_success = sum(1 for e in rounds if e.round_success)
    lines = [
        f"# {run_dir.name}  rounds {round_lo}-{round_hi}  "
        f"round_success={n_success}/{len(rounds)}"
    ]
    for evidence in rounds:
        verdict = "PASS" if evidence.round_success else "FAIL"
        n_attempts = len(evidence.attempts)
        n_pass = sum(1 for a in evidence.attempts if a.judge_match)
        lines.append("")
        lines.append(
            f"== R{evidence.round_number}  [{verdict}: {evidence.round_reason}]  "
            f"attempts={n_pass}/{n_attempts}✓  {evidence.failure_name}  "
            f"{evidence.stellar_reading}"
        )
        for message in evidence.link_messages:
            tag = "FO" if message.sender == "field_observer" else "SE"
            lines.append(f"   [{tag}] {message.text}")
        for index, attempt in enumerate(evidence.attempts):
            mark = "✓" if attempt.judge_match else "✗"
            lines.append(f"   ACTION{index + 1} {mark}: {attempt.action}")
            lines.append(f"      expected: {attempt.expected}")
    return "\n".join(lines)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--round-lo", type=int, default=16)
    parser.add_argument("--round-hi", type=int, default=25)
    args = parser.parse_args()
    print(render(run_dir=args.run_dir, round_lo=args.round_lo, round_hi=args.round_hi))


if __name__ == "__main__":
    main()
