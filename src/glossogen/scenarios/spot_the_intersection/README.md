# spot_the_intersection

Finding the common object across private boards. Each team has `team_size`
viewers, and each viewer holds a board of objects: a shape and a color in one
cell of a grid whose cells every board names the same way (`C4`). Exactly one
object is on every board of a team. The others are on some boards but not all,
so the viewers talk on their team's link channel until they can tell which one
they all hold, and then every member submits it.

`team_size` sets the viewers per team, from 2 to 12. Boards grow with the team,
so the grid has to grow too. With the presets' decoy and filler draws, the
smallest grids accepted are 6×6 for 3 or 4 viewers, 7×7 for 5 to 10, and 8×8 for
11 or 12. Two viewers need decoys off (`decoy_count_values: [0]` and
`decoy_count_weights: [1]`), and then 5×5. The presets' own 6×6 grid fits 3 or 4
as shipped, and 2 with decoys off.

With `near_misses` on (the default), certification requires that leaving out
any one board leaves at least two candidates, so every viewer is needed to find
the answer.

## Task and scoring

- A viewer calls `submit_object(shape, color, cell)` once per round. A
  submission cannot be changed, and the tool never says whether it was right.
  One that arrives after the round has been scored is refused.
- A team is correct only when **every** member submitted the common object. A
  member who never submits, or who names anything else, loses the round for the
  team. Scoring is deterministic; there is no judge.
- Two teams (the default) play the same boards seat for seat on isolated links.
  Among correct teams, the one that sent the fewest link characters wins, and
  ties are shared. Each team is told its result on its link when the round
  ends, and again in the discussion-phase briefing and the next round's.
- Characters stop counting once a team's last member submits.
  `round_time_budget_seconds` is an optional hard cap (`-1`, the default, is
  none).

## How a round is built

Each round is planted in this order, from a random stream keyed by the seed and
the round number:

1. **The answer**, on every board.
2. **Near-misses** (with `near_misses` on and three or more viewers): one per
   viewer, on every board except that viewer's. The board missing it holds a
   *stand-in* in the same cell, differing in one attribute. Without any one
   viewer, at least two candidates remain.
3. **Cell twins**: two cells every board fills, one with the shape the same on
   all boards and one with the color the same, never the whole object.
4. **Look twins**: two shape-and-color pairs every board holds, not all in one
   cell. They are drawn from every look, the answer's included.
5. **Decoys** (`decoy_count_*`): objects on more than one board and fewer than
   all.
6. **Fillers** (`filler_count_*`): objects on one board, until every board holds
   the same number.

No placement repeats an object another board already holds in that cell, so
each object is held by exactly the boards it was planted on. Each board's lines
are then shuffled from a separate random stream, so the answer's position in the
list is independent of the board's contents.

Cell and look twins exist so that comparing only part of an object never
isolates the answer: cells alone, shape and color alone, shape with cell, and
color with cell each leave at least two values every board holds.

## Certification

Every check runs on what the viewers read.

- **Certified from the lines the viewers read.** `board_certification.py` parses
  the rendered lines back and checks the properties above, plus that the declared
  objects are exactly the objects on the boards. It never reads the generator's
  boards. A round that fails is redrawn; one that never passes raises
  `BoardGenerationError` and the run does not start.
- **The certifier is tested by breaking rounds.** `test_board_certification.py`
  takes certified rounds and breaks one property at a time (a second common
  object, a board that rules nothing out, a declaration that does not match, an
  unreadable line) and requires the certifier to name it.
- **No single-board guesser beats chance.** `single_board_guessers.py` runs
  guessers that see one board alone: first listed, last listed, rarest look, most
  common look, most common color, most common shape, nearest the centre, and most
  crowded row. It flags one that beats chance by more than four standard errors,
  clustered by round, or that is right on every board. Other ways of exploiting a
  board are not tested.

### Before a cohort

Sweep the presets' board settings at every team size, on the preset's own grid
when the boards fit there and on the smallest grid the knobs accept. Presets
whose boards are identical, such as the two shipped ones (board generation does
not read `two_teams`), are swept once:

```bash
VIRTUAL_ENV= uv run --no-sync python -m \
  glossogen.scenarios.spot_the_intersection.scripts.certify_boards --seed-count 200
```

It exits non-zero if any round fails to generate or re-certify, or any
single-board guesser beats chance.

### After the first runs

Audit what the viewers were actually sent, from each run's event log:

```bash
VIRTUAL_ENV= uv run --no-sync python -m \
  glossogen.scenarios.spot_the_intersection.scripts.audit_recorded_boards \
  runs/spot_the_intersection/<run_id> [...]
```

It requires every viewer's injected board to match the board recorded for its
seat, both teams to have been sent the same boards, and the boards as sent to
certify. A team with a viewer who was sent no board is reported once and not
certified further. It also notes rounds whose recorded boards differ from what
the current checkout generates, or that it cannot generate, which happens when
generation changed between two cohorts sharing a seed.

Then compare round success round by round. Runs sharing a seed and board knobs
play identical boards (generation is keyed by seed and round number), so a round
whose mean `round_success` sits far below the others is a candidate for a bad
board:

```bash
glossogen analyze --runs-dir ./runs --scenario spot_the_intersection --label <cohort> \
  --grain round --group-by round_number \
  --measure round_success_team_a:mean --measure round_success_team_b:mean
```

## What viewers are told

The system prompt states the grid and its cell names, that exactly one object is
on every board, the submission rule, and the competition. It does not mention
near-misses, twins, decoys, or that every board is needed. Each round's briefing
lists the viewer's own board and the previous round's result, never the answer.

## Modes

- `two_teams: true` (`knobs_default.json`): two teams on isolated `link_a` /
  `link_b`, competing on the same boards.
- `two_teams: false` (`knobs_single_team.json`): one team on `link`; the
  character count is the score.
- `simulated_opponent_ratio: [0.75, 0.85]` with `two_teams: true`
  (`knobs_simulated_opponent.json`): Team A plays alone against a simulated
  Team B. Team B gets every round right in a share of Team A's link characters
  drawn each round between 0.75 and 0.85, rounded down, so a correct Team A
  loses every round by that margin. The share is drawn from the seed and the
  round number in steps of a thousandth of the range, so a resumed run scores
  each round as it was played, and runs with the same seed see the same shares.
  Team A's viewers hold the same ids, channels, system prompt, briefings and
  result messages as in a real two-team run, so nothing they read differs; only
  the recorded verdict reason names the opponent as simulated. Above 1 the share
  lets a correct Team A win every round. The run's description, logged at its
  start, says Team B was simulated.

## Key knobs

- `team_size`: viewers per team, 2 to 12.
- `simulated_opponent_ratio`: `null` plays both teams. With `two_teams: true`,
  a positive number simulates Team B at that fixed share of Team A's characters,
  and a `[low, high]` pair with `0 < low <= high` draws the share each round in
  that range.
- `grid_size`: the grid needs at least twice as many cells as the largest board.
- `near_misses`: whether every board is required. Off, some viewers may be left
  out of a round without loss.
- `decoy_count_values` / `_weights` and `filler_count_values` / `_weights`: drawn
  per round. A board holds the planted objects (five, plus one per viewer with
  near-misses on and three or more viewers) plus both counts, so a board missing
  a decoy holds an extra filler in its place. Decoys need three viewers, so set
  `decoy_count_values: [0]` and `decoy_count_weights: [1]` for `team_size: 2`.
- `round_time_budget_seconds`, `channel_noise_level`, `noise_replacement_mode`,
  and the postmortem knobs, as in other scenarios.

## Recorded events

- `spot_the_intersection_round_started`: every board as read, every object with
  its kind and the seats holding it, the answer, and the certificate: candidates
  left without each seat, the partial-comparison counts, the generation attempts,
  and two reference costs in object mentions (every board listed in full, and
  each viewer in turn listing what survives on its board).
- `intersection_submission_recorded`: each submission, whether it was the answer,
  and the team's character count at that moment.

## Metrics

All generic: `round_success` (`_team_a` / `_team_b` with two teams),
`round_success_after_resume`, the per-team character and language metrics on
each team's link, `communication_*` via `build_communication_rounds`, and the
`protocol_*` family via `get_protocol_probe_config` /
`get_protocol_explanation_config`.

`protocol_probe` asks each viewer what it would send first for each board in
`protocol_probe_questions.json`: seat 1's board of rounds 9, 6 and 10 of seed 3
under the default preset, holding 12, 15 and 18 objects (the preset's smallest,
middle and largest board sizes). The presets play seed 42, so a viewer has not
been sent these boards in a run on them. `test_protocol_probe_questions.py` holds
the file to those generated boards. A run on another grid is probed
with the same boards, so on a grid smaller than 6×6 some of their cells lie off
the run's grid.

## Files

- `board_model.py`, `board_rendering.py`: objects, cell names, and the line
  format with its exact inverse.
- `board_generation.py`, `board_certification.py`: planting and certification.
- `single_board_guessers.py`: the single-board leak check.
- `recorded_board_audit.py`, `scripts/audit_recorded_boards.py`: the recorded-run
  audit.
- `scripts/certify_boards.py`: the sweep before a cohort.
- `world.py`, `world_state.py`, `outcome_reconstruction.py`: character metering,
  submissions and locking, scoring, and on resume, rebuilding outcomes from the
  recorded answers and continuing a round the run stopped in.
- `tools.py`, `team_declaration.py`, `seats.py`, `injection_rendering.py`,
  `round_event_conversion.py`, `events.py`: the tool, roster, prompts, and events.
- `run_detail_extension.py`: the run page's round data. The round timeline
  (`frontend/src/features/runs/spot_the_intersection/`) draws every seat's board
  as its viewers read it, with the answer and the near-misses marked, and each
  team's submissions and result.
