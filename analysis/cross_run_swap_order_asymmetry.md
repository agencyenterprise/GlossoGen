# Why order matters in sonnet-pair cross-run swaps

Analysis of 18 cross-run replace-agent runs labelled `sonnet_pair`, comparing the two import directions between source runs `1777488131` (S131) and `1777488134` (S134) at round_start ∈ {10, 15, 20}.

## Mechanics (what is persisted across the swap)

In a cross-run replace-agent with `postmortem_disabled_at_start: true`:

• Sim A's `stabilization_engineer` keeps their *full pydantic-ai history* from Sim A.
• The imported `field_observer` arrives with their *full pydantic-ai history* from Sim B (their own messages, their old engineer's replies, their old postmortems).
• Both agents land on Sim A's `link` channel state at round `round_start`; postmortem is closed so they cannot renegotiate.
• The two pre-resume protocols have to interoperate live, with the engineer in the dominant role (they own the per-round stellar reading and emit every instruction).

## The two source teams developed incompatible observer dialects

Both sources used identical knobs (seed=42, sonnet, 25 rounds, 450-char budget, postmortem on). What diverged is purely the observer's communication style.

*S131* (`runs/veyru/1777488131`):
• Observer reports *symbolic symptoms*: `AllF+.Hlay.someFxNTR`, `1F+vib.Hwhine`, `F-drift. E blur. H~.`, `C+click.Thot`.
• Status words are *English tokens*: `Stable.` (16 occurrences in source), `Ineff.`. Never lone `f` / `r`.
• Engineer instructions are verbose with em-dashes: `"Bell front face, then opposite — 15s pause — 5 cycles moderate"`.

*S134* (`runs/veyru/1777488134`):
• Observer *pre-diagnoses* with 2-letter motif codes: `V19: cs`, `New: ec`, `New: cd`, `V24: ps`.
• Status uses a *1-char feedback protocol*: 12 lone `f` (fail), 10 lone `r` (engineer-reply retry). Locked in by mutual postmortem agreement at the end of R9 ("Let's use 'f' instead of 'fail'").
• Engineer instructions are abbreviated with slash separators: `Bl Bk-face firm 5cyc 8s pause / Cool Cl 8s / fan firm L+R 8s`.

## Result table (rounds 10/15/20 onward, 3 reps each)

```
Direction (A=engineer kept, B=observer imported)     rs=10   rs=15   rs=20   source-A baseline window
A=131, B=134  (134-OBS into 131-ENG)                  0.50    0.36    0.28    0.81 / 0.73 / 0.83
A=134, B=131  (131-OBS into 134-ENG)                  0.81    0.61    0.72    0.75 / 0.64 / 0.67
```

The bad direction loses 31–56 percentage points relative to the source; the good direction tracks the source within ±6 points. And the bad direction gets *worse with later rs*, which is the tell.

## Why the asymmetry: the f/r protocol is brittle in one direction only

Counted lone-`f` and lone-`r` link messages in the post-resume runs:

```
run         direction               rs   lone f   lone r   clarif msgs
1778007164  131-ENG ← 134-OBS       15        9        0             2
1778006739  131-ENG ← 134-OBS       15        3        0             0
1778005805  131-ENG ← 134-OBS       15        2        0             1
1778005775  134-ENG ← 131-OBS       15        0       13             0
1778005837  134-ENG ← 131-OBS       15        0        8             0
1778007014  134-ENG ← 131-OBS       15        0        4             0
```

### When 134-OBS lands at 131-ENG (the bad direction)

• The observer keeps reflexively sending `f` on failed stabilizations. The engineer has never seen `f` and asks back: in run 1778007164 R16 the engineer literally writes _"Did 'f' mean done/stable or failed? Confirm."_ — and again in R20: _"(Report symptoms only — no stray keys)"_.
• Clarification exchanges cost 50–150 chars on a 450-char budget. R15 collapses outright in 2/3 of these runs, R16/R17 cascade, the rest of the window degrades.
• The observer also expects terse abbreviated step instructions (`Bl Bk-face firm 5cyc 8s`); the 131 engineer keeps sending verbose English, so the observer's `stabilize_veyru` description is sometimes a guess and triggers retries.

### When 131-OBS lands at 134-ENG (the benign direction)

• Observer sends `Stable.` / `Ineff.` / `AllF+.Hlay.FxNTR`. These are well-formed; the 134 engineer can decode them cold (they always knew the symptom→motif mapping; the codes were a convenience, not a requirement).
• 134-ENG keeps emitting `r` after observer's `Ineff.` — a one-sided remnant of their old protocol, but harmless: the observer just retries because the next instruction follows.
• No engineer-side clarifications, no stray-key cleanup. Same hard rounds collapse (R16/R17 collapse in _both_ sources too) but no protocol overhead piles on.

## Why the harm grows with round_start

The lone-`f` count by `round_start` confirms this: at rs=10 the imported 134-OBS sends *0* lone `f` (S134 only adopted f/r in their R9 postmortem — `source_b_round_end=9`, just before commitment). At rs=15 and rs=20, the imported observer is fully committed. Mean rsar in the bad direction tracks this exactly: 0.50 → 0.36 → 0.28. The good direction is flat at ~0.69 because S131's observer style doesn't have a "phase transition" in the same way.

## One-sentence takeaway

The asymmetry isn't about which team is "stronger" — both sources score similarly. It's that *S134's observer dialect is brittle* (relies on partner reciprocation of 1-char codes and abbreviated instructions) while *S131's observer dialect is robust* (well-formed English+symbols any engineer can read); importing the brittle one into the stranger team produces parsing failures every round on a fixed character budget, and the team dies on overhead before they ever execute the procedure.

## Implication for the experiment design

Cross-team swap results are not directionally symmetric even between same-model runs. To compare two sources cleanly, run *both directions* at every `round_start` and report the pair, not a single number. A single direction confounds "did the imported agent generalize?" with "is the receiving engineer compatible with the imported observer's protocol?".
