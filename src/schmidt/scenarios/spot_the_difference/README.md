# spot_the_difference

Reconstruction-from-split-data scenario. Each team has two symmetric **viewers**:
the left viewer sees scene A, the right viewer sees scene B — two near-identical
scenes of objects (a shape with a size and color). The environment plants exactly
**K** differences in scene B from a fixed taxonomy (attribute changed, object
moved, object added, object removed). Neither viewer sees the other scene or the
differences, so a difference is only discoverable by exchanging descriptions over
the link channel.

The scenario is tuned so this requires genuine collaborative grounding rather
than a serialize-and-diff dump:

- **Duplicates.** The attribute vocabulary is small (4 shapes × 4 colors × 2
  sizes), so at the scene sizes used here identical objects recur. A bundle does
  not identify an object — position does.
- **Relational positions, no coordinates.** Agents see each object only as a
  coarse 3×3 region plus relations to other objects in their own scene ("a small
  red square to its left"). The anchors are possibly-duplicate objects in a
  layout that differs between the two scenes, so the two viewers' descriptions
  do not align one-to-one.
- **Optional character budget.** `round_time_budget_seconds` is an optional hard
  cap: when positive, every character a team sends on the link channel counts
  against it and exceeding it makes the team ineligible for the round. The
  default is `-1` (no cap) — the competitive fewest-characters-wins objective
  already pressures teams to stay terse.

## Task & scoring

- A viewer calls `submit_differences(differences)` with one **plain-English**
  line per difference. The first submission locks the team's answer.
- The submission is scored by the **naive-reader judge** (`difference_judge.py` /
  `prompts/difference_judge.jinja`, haiku): it judges each item on its own,
  without using the ground truth as a decoding key, and **rejects** any item
  whose object, position, or change is carried only by codes, coordinates, or
  invented shorthand — so the compression pressure stays on the link chat, not
  the submission. Ambiguous items (attributes shared by several objects with no
  position) and items matching no real difference are false positives.
- **Gate:** a team is eligible only if it identifies every difference, with no
  false positives (and within budget when one is set).
- **Objective:** among eligible teams, fewest link-channel characters wins; the
  winner is announced at the start of the next round as in-context
  reinforcement. Single-team mode keeps the character total as the score.

## Modes

- `two_teams: true` (default preset) — two isolated teams (`link_a` / `link_b`)
  on the identical seeded scenes each round.
- `two_teams: false` (`knobs_single_team.json`) — one team; no rival.
- `shared_link: true` (two-team only) — both teams share ONE link channel (all
  four viewers are members) instead of `link_a` / `link_b`, so each team can read
  the other's link messages; the `postmortem_a` / `postmortem_b` channels stay
  private. Each team is still charged only for its own members' characters (the
  win rule is unchanged), and the viewer prompts state that the opposing team can
  see everything posted on the shared link.

## Key knobs

- `grid_size`, `object_count_*`, `difference_count_*` — scene size and K
  distribution. `easy_round_numbers` forces K=1 (warmup).
- `round_time_budget_seconds` — optional per-round link-channel character cap
  (`-1` = no cap, the default).
- `difference_kinds` — the enabled taxonomy subset.
- `all_must_submit` (default `true`) — both teammates must each call
  `submit_differences` (the round is lost for any team where one member never
  submits), both answers are judged, and the team is eligible only if the two
  answers agree on the same full set of differences with no false positives.
  Set `false` to let the first submission from either member lock and score the
  team.
- `channel_noise_level` / `noise_replacement_mode` — per-character link noise.
- `judge_model` / `judge_provider` — the submission judge.

## Metrics

All scoring is generic: `round_success` (+ `_team_a` / `_team_b`),
`round_success_after_resume`, `mean_chars_per_round`, `mean_chars_per_message`,
the language-emergence family, `communication_*`, and the `protocol_*` family
(via `get_protocol_probe_config` / `get_protocol_explanation_config`).

## Files

- `scene_generation.py` — seeded scene + K-difference planting, region/relation
  rendering, relational ground-truth descriptions (no LLM).
- `world.py` / `world_state.py` — per-team character accounting, hard-budget
  enforcement, submission locking, correctness-gate + fewest-characters scoring.
- `difference_judge.py` / `mcp_tools.py` — the `submit_differences` naive-reader judge.
- `scripts/check_scene_generation.py` — generation determinism/correctness check
  (duplicates occur, moves cross regions, descriptions present).
