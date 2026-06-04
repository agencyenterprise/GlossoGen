"""Build a balanced validation set for the Veyru stabilization judge.

Produces a small labeled set used to check whether a candidate judge (new prompt
or new model) agrees with the reference verdict. Three columns only:

  * ``expected_input`` — the stabilization procedure the engineer had to convey
    (``expected_actions``),
  * ``input`` — what the field observer reported (``observer_action``),
  * ``is_match`` — the reference answer key.

Rows come in three flavours, all read from the replay ``pair_cache.jsonl``
produced by ``scripts/replay_veyru_judge.py`` (which re-judged, under the fixed
prompt, every pair the original judge had accepted):

  * ``is_match=True`` — both the original and the fixed judge accepted the pair
    (a confident genuine match).
  * ``is_match=False`` flip — the original judge accepted but the fixed judge
    rejected (a subtle over-acceptance the prompt fix corrected).
  * ``is_match=False`` clear-negative — *synthesized*: a real procedure's
    ``expected_input`` paired with a well-formed observer action drawn from a
    clearly-different procedure (low token overlap). The action is natural text
    but performs the wrong procedure, so it is an unambiguous non-match that
    relies on no judge's verdict.

The set is balanced (equal True / False) so a judge that always answers one way
cannot score well. Sampling and synthesis are seeded for reproducibility.
"""

import argparse
import csv
import json
import random
import re
from pathlib import Path
from typing import NamedTuple

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[2]
PAIR_CACHE = REPO_ROOT / "runs" / "_judge_replay" / "pair_cache.jsonl"
DEFAULT_OUTPUT = SCRIPT_DIR / "judge_validation_set.csv"
SAMPLE_SEED = 42

# Maximum word-overlap (Jaccard) between two procedures' expected_actions for a
# synthesized clear-negative to count as "clearly different". Veyru procedures
# share boilerplate ("the", "face", "seconds"); genuinely different ones still
# fall well under this, so a low cap guarantees the mismatch is unambiguous.
_CLEAR_NEGATIVE_MAX_JACCARD = 0.45


class ValidationExample(NamedTuple):
    """One row of the judge validation set."""

    expected_input: str
    input: str
    is_match: bool


class ReferencePair(NamedTuple):
    """A cached (expected, observer) pair with the fixed judge's verdict."""

    expected_actions: str
    observer_action: str
    new_match: bool


def load_reference_pairs(pair_cache_path: Path) -> list[ReferencePair]:
    """Read ``pair_cache.jsonl`` into pairs, dropping errored or blank-input rows."""
    pairs: list[ReferencePair] = []
    for line in pair_cache_path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        new_match = row.get("new_match")
        expected = row.get("expected_actions", "").strip()
        observer = row.get("observer_action", "").strip()
        if new_match is None or not expected or not observer:
            continue
        pairs.append(
            ReferencePair(
                expected_actions=row["expected_actions"],
                observer_action=row["observer_action"],
                new_match=bool(new_match),
            )
        )
    return pairs


def _tokens(text: str) -> set[str]:
    """Lowercased alphanumeric word set, for procedure-similarity comparison."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _jaccard(left: set[str], right: set[str]) -> float:
    """Jaccard overlap of two token sets; 0.0 when either is empty."""
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def synthesize_clear_negatives(
    source: list[ReferencePair],
    existing_real_pairs: set[tuple[str, str]],
    count: int,
    seed: int,
) -> list[ValidationExample]:
    """Build ``count`` unambiguous non-matches by cross-pairing different procedures.

    Each negative takes one pair's ``expected_actions`` and another pair's
    ``observer_action`` where the two procedures' expected texts overlap little
    (``_jaccard`` below the cap), so the borrowed action plainly performs the
    wrong procedure. Pairings that coincide with a real cached pair, or that
    repeat, are rejected.
    """
    rng = random.Random(seed)
    token_cache = {pair.expected_actions: _tokens(pair.expected_actions) for pair in source}
    out: list[ValidationExample] = []
    seen: set[tuple[str, str]] = set()
    attempts = 0
    max_attempts = count * 200
    while len(out) < count and attempts < max_attempts:
        attempts += 1
        target = rng.choice(source)
        donor = rng.choice(source)
        if target.expected_actions == donor.expected_actions:
            continue
        pair_key = (target.expected_actions, donor.observer_action)
        if pair_key in existing_real_pairs or pair_key in seen:
            continue
        overlap = _jaccard(
            token_cache[target.expected_actions], token_cache[donor.expected_actions]
        )
        if overlap > _CLEAR_NEGATIVE_MAX_JACCARD:
            continue
        seen.add(pair_key)
        out.append(
            ValidationExample(
                expected_input=target.expected_actions,
                input=donor.observer_action,
                is_match=False,
            )
        )
    return out


def build_dataset(
    pairs: list[ReferencePair], per_class: int, clear_negatives: int, seed: int
) -> list[ValidationExample]:
    """Assemble the balanced set: ``per_class`` True, ``per_class`` False (flips + clear).

    The False half is ``clear_negatives`` synthesized clear-negatives plus
    ``per_class - clear_negatives`` real flips. Everything is sampled/shuffled
    under ``seed``.
    """
    if clear_negatives > per_class:
        raise ValueError(
            f"clear_negatives ({clear_negatives}) cannot exceed per_class ({per_class})"
        )
    matches = [pair for pair in pairs if pair.new_match]
    flips = [pair for pair in pairs if not pair.new_match]
    rng = random.Random(seed)

    flip_quota = per_class - clear_negatives
    chosen_true = [
        ValidationExample(expected_input=p.expected_actions, input=p.observer_action, is_match=True)
        for p in rng.sample(matches, min(per_class, len(matches)))
    ]
    chosen_flips = [
        ValidationExample(
            expected_input=p.expected_actions, input=p.observer_action, is_match=False
        )
        for p in rng.sample(flips, min(flip_quota, len(flips)))
    ]
    real_pair_keys = {(p.expected_actions, p.observer_action) for p in pairs}
    chosen_clear = synthesize_clear_negatives(
        source=matches,
        existing_real_pairs=real_pair_keys,
        count=clear_negatives,
        seed=seed,
    )
    combined = chosen_true + chosen_flips + chosen_clear
    rng.shuffle(combined)
    return combined


def write_csv(rows: list[ValidationExample], output_path: Path) -> None:
    """Write the three-column validation CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["expected_input", "input", "is_match"])
        for row in rows:
            writer.writerow([row.expected_input, row.input, row.is_match])


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the validation-set builder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"CSV output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--per-class",
        type=int,
        default=250,
        help="Count of is_match=True and of is_match=False examples each (default: 250).",
    )
    parser.add_argument(
        "--clear-negatives",
        type=int,
        default=100,
        help="How many of the is_match=False half are synthesized clear-negatives (default: 100).",
    )
    return parser.parse_args()


def main() -> None:
    """Build and write the balanced judge validation set."""
    args = parse_args()
    pairs = load_reference_pairs(pair_cache_path=PAIR_CACHE)
    rows = build_dataset(
        pairs=pairs,
        per_class=args.per_class,
        clear_negatives=args.clear_negatives,
        seed=SAMPLE_SEED,
    )
    true_count = sum(1 for row in rows if row.is_match)
    print(
        f"Wrote {len(rows)} rows ({true_count} is_match=True, "
        f"{len(rows) - true_count} is_match=False; {args.clear_negatives} of the False "
        f"are synthesized clear-negatives) to {args.output}"
    )
    write_csv(rows=rows, output_path=args.output)


if __name__ == "__main__":
    main()
