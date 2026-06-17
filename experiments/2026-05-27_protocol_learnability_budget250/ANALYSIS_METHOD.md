# Per-baseline protocol-learnability run analysis — method

A repeatable procedure for analyzing the runs derived from a single veyru
baseline (the `src=veyru/<ts>` family) and explaining *why* a swapped-in field
observer did or did not reconstruct the team's protocol. Designed to be applied
to any interesting baseline, not just one.

Tool: [`dump_post_swap_transcript.py`](dump_post_swap_transcript.py) — renders,
per round in a window (default 16–25), the case + stellar parameters, the
verbatim `link` exchange, the observer's `stabilize_veyru` action(s), the
per-attempt judge verdict, and the authoritative round outcome
(`round_result_recorded`: `stabilized` vs `Veyru collapsed`).

## Why this works

Only the **field observer is swapped**. The **stabilization engineer is
unchanged** and keeps emitting whatever compressed protocol the baseline
evolved. So the derived run is a clean test of one thing: *can a newcomer read
the engineer's compressed messages and execute them?* The observer is also the
only agent that calls `stabilize_veyru`, and the judge scores its action on
action-type + face + duration + intensity. Therefore the observer must **decode**
the engineer's code into a fully-parameterized physical action — comprehension
and application are both observable in one place.

## Step 0 — enumerate the derived family and pull the headline numbers

For the baseline `src`, list every derived run with `(phase, history, observer,
round_success over 16–25)`. Group by `(phase, history, observer)`; each cell
should have 3 replicas. This gives the map of *what to explain* (which cells are
high, which are low, which replicas diverge within a cell). Scope to the
condition of interest first (e.g. `phase=replace_learned`, `history=10`,
same-model).

## Step 1 — reconstruct the baseline protocol (rounds 1–15)

Dump the baseline's own `link` channel by round. Identify:

- **The observer's symptom vocabulary** — how verbose descriptions collapse into
  single-word motif codes (e.g. `leak`, `deadlock`, `drift`, `core`).
- **The engineer's procedure code system** — the compact instruction format and
  what each field means (this baseline: `P<n> <face> <dur> <intensity>`, e.g.
  `P13 L 8 g`).
- **The repair convention** — what the team does when a code fails or is
  unclear (this baseline: the observer says `spell out` / `Pn?` and the engineer
  re-sends the full procedure).
- **The codebook coverage** — *which codes were ever spelled out (defined) inside
  the window the newcomer will see.* A code used post-swap but never defined in
  the visible window is **un-cached**: the newcomer cannot decode it without a
  spell-out. Grep the window for each `Pn` to build the cached/un-cached set.

## Step 2 — per-run, walk rounds 16–25

For each derived run in the cell, read the dump and classify every round:

1. **Comprehension** — did the observer map the engineer's code to the right
   action type? (judge ✓ on action-type/face, ignoring a wrong parameter.)
2. **Application** — were face / duration / intensity correct? (full judge ✓.)
3. **Repair** — when it hit an un-cached code, did it (a) decode correctly
   anyway, (b) ask first (`Pn?` / `spell`) then execute, or (c) guess wrong, then
   ask, then correct? (a)→(c) is increasing budget cost.
4. **Round outcome** — `stabilized` or `Veyru collapsed`. Cross-check against the
   attempt pass-rate: a round can be `collapsed` with *all attempts passing* —
   that is a **budget failure**, not a comprehension failure.

## Step 3 — separate the two failure modes

Every failed round is one of:

- **Comprehension/application failure** — an attempt was judged ✗ (wrong action,
  face, duration, or intensity) and never corrected → the protocol did not
  transfer for that case.
- **Budget collapse** — attempts passed but cumulative `link` characters exceeded
  the round budget. Usually concentrated on **high-motif rounds** (4–5 motifs at
  the same fixed budget) and amplified by spell-out repairs for un-cached codes.

The split is the core result: a newcomer can comprehend the protocol perfectly
and still lose rounds to the *cost* of the repairs comprehension required.

### Budget mechanics (how to read a collapse)

Verified from the event log — keep these facts in mind when attributing a
collapse, because the naive reading ("it ran out of time / acted too slowly") is
wrong:

- The budget counts **only `link` `send_message` characters**. The
  `stabilize_veyru` action texts (~150–200 chars each) do **not** count against it.
- A round is `veyru_collapsed` the moment **cumulative link characters cross the
  budget** (250 here), on whichever message tips it over.
- A multi-motif round needs **one passing stabilization per motif**. If the budget
  is spent before a motif has even been communicated, that motif gets **no action
  at all**.

So a round can show **every made-attempt passing the judge and still collapse**:
it means there were **fewer attempts than motifs** — the link ran out of
characters first, almost always because a **verbose spell-out of an un-cached
code** ate most of the budget in one message. It is *not* "correct actions arrived
too slowly"; actions don't consume the budget.

Worked example — R18 of 1779929383 (5 motifs, 3/3 attempts ✓, yet collapsed):

```
[FO] stall      5c   cum 5      [FO] spell P14   9c   cum 54
[SE] P2 L 20 g  9c   cum 14     [SE] <187c spell-out of P14> cum 241   ← 75% of budget
[FO] core       4c   cum 18     [FO] chaos       5c   cum 246
[SE] P5 L 20 g  9c   cum 27     [SE] P6 L 20 g   9c   cum 255 → collapse
[FO] deadlock   8c   cum 35
[SE] P14 L 20 g 10c  cum 45     # only 3 of 5 motifs ever reached a stabilize call
```

To attribute a collapse, sum the per-message link character counts and find the
message that crossed the budget — it is usually a single un-cached-code spell-out.

## Step 4 — explain within-cell variance

Replicas in the same cell share the case set (seed=42) and the engineer's
messages, so divergence is the newcomer's own behavior. Typical driver here:
**repair efficiency** on un-cached codes — ask-before-acting (cheap, survives a
tight round) vs guess-then-ask (an extra wasted `stabilize` attempt + comms tips
a 5-motif round into collapse).

## Reasoning checklist (the questions every per-run writeup answers)

- Did it adopt the symptom vocabulary? (first post-swap round is the tell.)
- Did it decode the engineer's code format, including parameters?
- Which codes were un-cached, and how did it handle each?
- Were the failures comprehension or budget?
- Where the round collapsed, what specifically cost the budget?
- What explains the gap vs the intact-team ceiling (`resume_expected`) and the
  no-postmortem arm (`resume_expected_no_postmortem`)?

## Commands

```bash
# Step 0 — derived family + post-swap round_success (window 16-25)
#   (parse labels.json: src=, phase=, history=, observer=; read veyru_report.json round_success per_round)

# Step 1 — baseline protocol
VIRTUAL_ENV= uv run --no-sync python experiments/2026-05-27_protocol_learnability_budget250/dump_post_swap_transcript.py \
  runs/veyru/<baseline_ts> --round-lo 1 --round-hi 15

# Step 2 — one derived run, full post-swap detail
VIRTUAL_ENV= uv run --no-sync python experiments/2026-05-27_protocol_learnability_budget250/dump_post_swap_transcript.py \
  runs/veyru/<derived_ts>

# round-verdict overview only
... dump_post_swap_transcript.py runs/veyru/<derived_ts> | grep -E '^#|^== R'
```
