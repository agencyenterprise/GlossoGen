# spot_the_difference

Reconstruction-from-split-data scenario. Each team has two symmetric **viewers**:
the left viewer sees scene A, the right viewer sees scene B — two near-identical
scenes of objects (`shape, color, size @ (column, row)`) on an `N×N` grid.
The environment plants exactly **K** differences in scene B drawn from a fixed
taxonomy (attribute changed, object moved, object added, object removed).
Neither viewer sees the other scene or the differences, so a difference is only
discoverable by exchanging descriptions over the link channel.

## Task & scoring

- A viewer calls `submit_differences(differences)` with one free-text line per
  difference. The first submission **locks** the team's answer for the round.
- An LLM judge (the canonical haiku judge) matches the submitted list against
  the K planted differences and counts false positives.
- **Correctness gate:** a team is eligible only if it identifies every
  difference with no false positives.
- **Objective:** the total characters a team sends on the link channel. In
  two-team mode, among eligible teams the one with the fewest characters wins;
  the winner is announced at the start of the next round as in-context
  reinforcement. In single-team mode the character total is simply the score to
  minimize. There is no hard character budget — characters never fail a round.

## Modes

- `two_teams: true` (default preset) — two isolated teams (`link_a` / `link_b`)
  on the identical seeded scene pair each round.
- `two_teams: false` (`knobs_single_team.json`) — one team; the rival is absent.

## Key knobs

- `grid_size`, `object_count_*`, `difference_count_*` — scene size and K
  distribution. `easy_round_numbers` forces K=1 (warmup).
- `difference_kinds` — the enabled taxonomy subset.
- `channel_noise_level` / `noise_replacement_mode` — per-character link noise.
- `judge_model` / `judge_provider` — the submission judge.

## Metrics

All scoring is generic: `round_success` (+ `_team_a` / `_team_b`),
`round_success_after_resume`, `mean_chars_per_round`, `mean_chars_per_message`,
the language-emergence family, `communication_*`, and the `protocol_*` family
(via `get_protocol_probe_config` / `get_protocol_explanation_config`).

## Files

- `scene_generation.py` — seeded scene + K-difference planting (no LLM).
- `world.py` / `world_state.py` — per-team character accounting, submission
  locking, the correctness-gate + fewest-characters round scoring.
- `difference_judge.py` / `mcp_tools.py` — the `submit_differences` LLM judge.
- `scripts/check_scene_generation.py` — generation determinism/correctness check.
