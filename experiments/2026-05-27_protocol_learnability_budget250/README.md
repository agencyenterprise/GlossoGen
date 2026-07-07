# Protocol learnability — replace-agent as a metric (budget=250, 2026-05-27)

## What we did, in plain English

We selected 10 baseline runs of 15 rounds each, for three models — Claude Sonnet 4.6,
Claude Opus 4.7, and GPT-5.4 — so 30 baseline runs in total. In each, a *field observer*
and a *stabilization engineer* worked together on the comm link with a tight
250-character-per-round budget, plus a free-form "team discussion" postmortem channel after
every round. Over the 15 rounds they developed a private communication protocol — shorthand,
codes, compressed phrasings — to stay under budget.

Then, for each baseline, we asked: **can a fresh field observer pick up that protocol just
by reading the link transcript?** We tested this three ways, all extending the run by 10
more rounds (rounds 16–25, identical seed-42 cases so every condition faces the same
problems).

- **Expected (3 resume runs)** — we resumed the original team verbatim (same observer, same
  engineer, postmortem still open) and let them keep playing. This gives the "ceiling": what
  the intact team naturally achieves on those 10 new rounds.
- **Expected, no postmortem (3 resume runs)** — same intact team, but the postmortem
  channel is killed going forward (`postmortem_disabled_at_start: true`). Isolates the
  "no postmortem" effect from the "fresh observer" effect: comparing this against Expected
  measures only the loss of the postmortem back-channel; comparing Learned against this
  measures only the fresh-observer effect.
- **Learned (3 replace runs)** — we swapped in a brand-new same-model field observer that
  had never seen this run, gave it only the **previous 10 rounds (5–14) of the link
  transcript** (no postmortem history, no postmortem going forward), and let it play with
  the original engineer. This is where the *replace-agent feature becomes the metric* —
  performance here measures whether the protocol is self-explanatory from the link alone.

- **Cross-family (3 replace runs)** — same as Learned, but the fresh observer is from
  the **other model family**: sonnet baselines and opus-4-7 baselines get a **gpt-5.4**
  observer; gpt-5.4 baselines get a **claude-opus-4-7** observer. Engineer stays on the
  baseline's original model. Everything else is identical to Learned (link history
  windowed to rounds 5–14, no postmortem). Isolates `Δ_family` — does a fresh
  *other-family* observer read the protocol better or worse than a fresh same-family
  observer?

That's 45 baselines + 135 resume + 135 resume_no_postmortem + 135 replace + 135 cross_family = 585 runs.

For each baseline we compare the four means. Decomposing `Δ_total = learned − expected`:

- `Δ_postmortem = expected_no_postmortem − expected` — loss from removing the postmortem
  back-channel alone (intact team, no fresh observer).
- `Δ_observer  = learned − expected_no_postmortem` — loss from swapping in a fresh observer
  alone (postmortem held constant: off in both arms).

A *small* `Δ_observer` means a fresh observer essentially matched the original team → the
protocol is **transferable**. A *big* `Δ_observer` means the original team's performance
depended on knowledge the newcomer couldn't recover from the transcript → the protocol is
**idiosyncratic**.

Finally, an LLM judge scored each baseline's link transcript against a 35-category
communication ontology (open-coded across all 30 baselines, then re-scored as a
feature-presence vector). Splitting baselines into the top-third and bottom-third by
*learned* score, we contrasted those feature vectors: features over-represented in the top
third are the ingredients of transferable protocols; features over-represented in the
bottom third are what makes a protocol private.

**Headline finding:** **named-code / motif-tagging protocols transfer**; **subtractive-compression
protocols don't**. If the team gives each failure motif a stable symbolic name ("K", "DR",
a specific token), a newcomer picks it up from context — every occurrence reinforces the
mapping. If instead they compress by dropping vowels, omitting steps, or assuming shared
context, the result is unreadable to anyone who wasn't there to build the shared ground.

## Goal

Discover **what makes one communication protocol "better" than another**. Each baseline
run produces a protocol the field observer + stabilization engineer develop on the
budget-constrained `link` channel. We score a protocol by **how well a fresh field
observer — dropped in with only the recent link transcript, no postmortem — keeps
stabilizing Veyrus**, and compare against the intact team continuing. Protocols a
newcomer can pick up and run with are the "good" ones; we then extract their
communication features.

## Cohort

- **Scenario / budget**: veyru, `round_time_budget_seconds=250`, 15 rounds, postmortem ON,
  `seed=42`, judge `claude-haiku-4-5-20251001`. Knobs: [`knobs_baseline.json`](knobs_baseline.json).
- **Models**: `claude-sonnet-4-6`, `claude-opus-4-7`, `gpt-5.4` — **15 baselines each (45 total)**.
  Of those, 10 sonnet + 10 opus are reused legacy baselines (pre-`easy_round_numbers` schema);
  the remaining 5 sonnet, 5 opus, 15 gpt-5.4 are fresh canon baselines launched for this experiment.
- **Expected (resume)**: each baseline resumed at round 15, **+10 rounds** (→ rounds 16–25),
  no config change (postmortem stays on, original observer continues). **3 per baseline (135)**.
- **Expected, no postmortem (resume)**: same resume, with
  `postmortem_disabled_at_start: true` ([`resume_no_postmortem_knobs.json`](resume_no_postmortem_knobs.json) /
  [`resume_no_postmortem_knobs_legacy.json`](resume_no_postmortem_knobs_legacy.json)). The
  intact team continues, but the postmortem channel is gone from round 16 on (no injections,
  no reads, no sends — both agents). **3 per baseline (135)**.
- **Learned (replace)**: `field_observer` replaced at round 15 with a fresh **same-model**
  observer; link history windowed to the **previous 10 rounds (5–14)** via
  `--history-from-round 5`; historical postmortem stripped + no new postmortem
  ([`replace_knobs.json`](replace_knobs.json)); **+10 rounds**. **3 per baseline (135)**.
- Comparison window: **rounds 16–25** (the 10 genuinely new, seed-42-identical cases).

Concurrency: **6 sims per provider** (anthropic = sonnet+opus shared cap; openai = gpt).

## Platform change this experiment introduced

`replace-agent` / the replace manifest now carry per-channel `channel_history_floors`,
exposed by the `--history-from-round R` CLI flag. A visible channel listed there is
reconstructed with `ChannelVisibilityFromRound(round_floor=R)` (the same windowing the
multi-swap `scheduled_events` use): `read_channel` calls dropped, `send_message` kept from
round R on, notifications floored at R. Validated structurally and with a haiku judge: the
replaced observer sees only link rounds 5–14 and no postmortem backchannel content.

## Labels

- baseline: `["protocol_learnability","phase=baseline","budget=250","model=<m>","rc=15"]`
- expected: `["protocol_learnability","phase=resume_expected","budget=250","model=<m>","history=10","src=<src>"]`
- expected_no_postmortem: `["protocol_learnability","phase=resume_expected_no_postmortem","budget=250","model=<m>","history=10","src=<src>"]`
- learned:  `["protocol_learnability","phase=replace_learned","budget=250","model=<m>","history=10","src=<src>"]`
- cross_family: `["protocol_learnability","phase=replace_cross_family","budget=250","model=<m>","observer=<o>","history=10","src=<src>"]`

(`<m>` ∈ {sonnet, opus47, gpt54} = the baseline's model; `<o>` ∈ {sonnet, opus47, gpt54}
= the cross-family observer's model — by table: sonnet→gpt54, opus47→gpt54, gpt54→opus47;
`<src>` = `veyru/<baseline_ts>`.)

## Launch

```bash
# Stage 1 — 45 baselines (per-provider cap 6). The 10 sonnet + 10 opus legacy
# baselines are reused from earlier runs and not (re)launched by this script;
# launch_baselines.sh + launch_baselines_gpt_topup.sh launch the canon batch.
nohup bash experiments/2026-05-27_protocol_learnability_budget250/launch_baselines.sh \
  > /tmp/protolearn_baselines.stdout 2>&1 & disown

# Stage 2 — 135 resume + 135 replace (run only after Stage 1 fully finishes)
nohup bash experiments/2026-05-27_protocol_learnability_budget250/launch_derived.sh \
  > /tmp/protolearn_derived.stdout 2>&1 & disown

# Stage 3 — 135 resume_expected_no_postmortem (isolates Δ_observer from Δ_postmortem)
nohup bash experiments/2026-05-27_protocol_learnability_budget250/launch_resume_no_postmortem.sh \
  > /tmp/protolearn_resume_no_postmortem.stdout 2>&1 & disown

# Stage 4 — 135 replace_cross_family.
nohup bash experiments/2026-05-27_protocol_learnability_budget250/launch_cross_family.sh \
  > /tmp/protolearn_cross_family.stdout 2>&1 & disown
```

**NEVER pin or modify the judge prompt.**
`src/glossogen/scenarios/veyru/prompts/stabilization_judge.jinja` must always be at **HEAD**
when running simulations. veyru judges stabilization **live during the simulation**, so
checking the prompt out to an older commit (or editing it) silently changes round outcomes
and corrupts every run launched against it. Do not `git checkout` or alter this file for a
run. (An earlier version of this doc wrongly instructed pinning it to `364987a` — that
guidance was incorrect and has been removed.)

`list_baselines.py` enumerates completed baselines (model/provider read from each run's
own `AgentRegistered`) and feeds Stage 2.

## Evaluation

Labels first, then (judge = haiku):

```bash
# round_success on every run (baselines score 1-15; derived score 15-25)
glossogen evaluate veyru --run-dir runs/veyru/<id> --metrics round_success,round_success_after_resume \
  --model claude-haiku-4-5-20251001 --provider anthropic

# feature extraction on the 30 baselines (the protocol lives in their link rounds 1-15)
glossogen evaluate veyru --run-dir runs/veyru/<baseline> --metrics communication_open_coding \
  --model claude-haiku-4-5-20251001 --provider anthropic
python scripts/consolidate_communication_ontology.py ...   # one ontology across the 30
glossogen evaluate veyru --run-dir runs/veyru/<baseline> --metrics communication_feature_presence \
  --model claude-haiku-4-5-20251001 --provider anthropic
```

## Analysis

The **Protocol learnability** streamlit tab (see Sources above) computes — per baseline —
the mean `round_success` over the selected rounds-window across its 3 resume
(`expected`) and 3 replace (`learned`) runs, derives `Δ = learned − expected`, ranks
baselines by `learned`, and contrasts `communication_feature_presence` vectors of the
high- vs low-learnability protocols to surface which features distinguish protocols a
newcomer can adopt.

## Runs

| Phase | Model | Count | Status |
|---|---|---|---|
| baseline | sonnet / opus47 / gpt54 | 15 / 15 / 15 | ✓ complete 2026-05-28 |
| resume_expected | per baseline ×3 | 135 | ✓ complete 2026-05-28 |
| replace_learned | per baseline ×3 | 135 | ✓ complete 2026-05-28 |
| resume_expected_no_postmortem | per baseline ×3 | 135 | ✓ complete 2026-06-01 |
| replace_cross_family | per baseline ×3 (sonnet→gpt54, opus47→gpt54, gpt54→opus47) | 135 | ⏳ launched 2026-06-01 |

## Results

Interactive view: open the **Protocol learnability** tab in the results-viewer
streamlit app (`make dev` then the analysis viewer). The tab carries a rounds-window
control, model multiselect, and three sub-tabs (Expected vs learned scatter, Feature
contrast bars, Full table). Sources: [`analysis/results_viewer/protocol_learnability_tab.py`](../../analysis/results_viewer/protocol_learnability_tab.py),
[`analysis/results_viewer/protocol_learnability_data.py`](../../analysis/results_viewer/protocol_learnability_data.py).

Per-model means over the rounds-16–25 comparison window (3 resume + 3 replace per source × 10 sources):

| Model | expected (resume) | learned (replace) | Δ (learned − expected) |
|---|---:|---:|---:|
| `gpt54` | 0.697 | 0.597 | **−0.100** |
| `sonnet` | 0.383 | 0.250 | −0.133 |
| `opus47` | 0.753 | 0.363 | **−0.390** |

gpt-5.4 protocols transfer the best to a fresh observer; opus-4-7 has the highest "expected"
ceiling but its protocols are the *least* recoverable from the link transcript alone.

### Features distinguishing high-learnability vs low-learnability protocols

Top contrasts from `communication_feature_presence` (mean confidence in top-third learners
minus bottom-third learners):

**More common in HIGH-learnability protocols (transferable):**

- `motif_code_naming` (+0.25) — named codes attached to specific failure motifs
- `compression_accelerates_across_rounds` (+0.19) — protocol tightens over time
- `multi_motif_serial_expansion` (+0.12) — multi-stage failures handled by serializing
- `procedure_code_substitution` (+0.12) — codes stand in for full procedures
- `asymmetric_role_compression` (+0.04)

**More common in LOW-learnability protocols (idiosyncratic):**

- `explicit_failure_signal` (−0.32) — verbose explicit failure descriptions
- `vowel_deletion_abbreviation` (−0.17) — dropped vowels
- `abbreviated_compound_formation` (−0.14)
- `capitalization_for_emphasis` (−0.11)
- `omission_of_intermediate_steps` (−0.11)

Interpretation: **symbolic / code-substitution protocols** (where each motif or procedure
gets a stable named token) are picked up by a fresh observer from the transcript;
**subtractive compression** protocols (vowel-deletion, omission) require shared context the
newcomer lacks. Ontology: `runs/veyru/_ontology/2026-05-28_protocol_learnability.json` (35 categories).
