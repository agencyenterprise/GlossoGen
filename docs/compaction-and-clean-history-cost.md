# Compaction & History-Cleanup: Cost & Behavior Findings

**Scope.** `clean_history` and provider-native `compaction` are **platform-wide** features — they apply to *every* scenario, not just the one measured here. The **data in this document, however, all comes from a single scenario: `drive_module_repair`.** So the *mechanisms and qualitative conclusions* generalize across scenarios, but the specific numbers (dollar costs, round_success, the exact rounds at which compaction fires) are `drive_module_repair`-specific and will differ per scenario depending on context growth rate, message volume, and task difficulty.

All runs: **seed 42, 15 rounds, budget 2000, haiku judge** (`claude-haiku-4-5-20251001`). Costs are each run's own platform accounting (`simulation_ended.total_cost_usd`, from `token_pricing.py`).

## TL;DR

- **`clean_history` (always-on history cleanup) is the dominant cost lever**, especially for gpt-5.4.
- **Compaction adds a lot only for sonnet** (−52% on top of clean_history); for gpt-5.4 it adds **~nothing** (−3%) because `clean_history` has already made the context lean.
- **Compaction reduces task success** — sonnet round_success 100%→61%, gpt-5.4 100%→87% (high variance) — a real quality tax. `clean_history` is quality-neutral.
- **Recommendation:** keep compaction **off by default** (it already is — opt-in). Enable on **Anthropic only** for cost-dominated / bulk work where losing a couple rounds of success is acceptable. Not worth enabling on OpenAI for this workload.

## What `clean_history` does

`clean_history` is an **always-on** history-cleanup step (no knob) applied to each agent's message history before every model call. It:

1. **Dedups `read_channel` messages** — successive `read_channel` calls re-return overlapping messages; each message is kept only in its earliest occurrence.
2. **Drops empty `read_notifications` round-trips** — the "no activity" polls that carry no information.

Net effect: each re-sent context is much smaller with **zero information loss** — which is why it's the dominant cost lever (it shrinks the context re-sent on every call). Measured directly, it roughly **halves** the reconstructed end-of-run context (~50%).

> **Separate, also always-on:** the `read_channel` tool itself now returns each message's time as a compact **elapsed-seconds float** instead of a long ISO timestamp (a source-level change to the tool, applied to all new runs — *not* part of `clean_history`). `clean_history` only *reads* `elapsed_seconds` as part of its dedup key. On old runs, the reconstruction path (`message_history_builder`) converts stored ISO strings to elapsed-seconds; that's also distinct from `clean_history`.

## Cost & quality by version, per model

Each cell: **mean cost** · round_success · ~mean messages (n runs).

| condition | gpt-5.4 | sonnet (claude-sonnet-4-6) |
|---|---|---|
| **old_version** (no clean_history, no compaction) | **$26.20** · rs **91%** · ~267 msgs (n=5) | **$36.46** · rs **100%** · ~279 msgs (n=5) |
| **clean_history** (no compaction) | **$14.04** · rs **100%** · ~247 msgs (n=1) | **$28.85** · rs **100%** · ~272 msgs (n=2) |
| **compaction=50000** (clean_history + compaction) | **$13.67** · rs **87%** · ~296 msgs (n=2) | **$13.79** · rs **61%** · ~257 msgs (n=5) |

**Message counts are comparable across all conditions (~247–296).** Since cost scales with messages exchanged, this confirms the cost differences reflect **context size** (clean_history / compaction), not different amounts of work — the comparison is fair.

### Step-by-step savings

Each cell: cost saving (round_success change).

| step | gpt-5.4 | sonnet |
|---|---|---|
| old_version → clean_history | **−$12.16 (−46%)** · rs 91%→100% | **−$7.61 (−21%)** · rs 100%→100% |
| clean_history → compaction | **−$0.37 (−3%)** · rs 100%→87% | **−$15.06 (−52%)** · rs 100%→61% |
| **old_version → compaction (total)** | **−$12.53 (−48%)** · rs 91%→87% | **−$22.67 (−62%)** · rs 100%→61% |

`clean_history` is quality-neutral (rs steady ~100%); **compaction is what costs round_success** — mildly on gpt-5.4 (−13pp) and heavily on sonnet (−39pp).

**Reading it:** clean_history is the big win for gpt-5.4; compaction is the big win for sonnet. Both paths converge to ~$13.7 despite very different starting points.

### Confound (important)

The `old_version` runs are on the **pre-clean_history codebase** (pydantic 1.89 + older token accounting); the clean_history/compaction runs are on current code (pydantic 2.4). So the `old_version → clean_history` delta **bundles the cleanup with the version/accounting change** — it's the real cost progression across versions, but not a clean isolation of `clean_history` alone. The only unconfounded way to isolate `clean_history` is a current-code run with cleanup disabled (not run).

## Does compaction work, and can we see it?

- **Both providers genuinely compact** once an agent's input crosses the threshold (**minimum 50,000 tokens**; below that the server silently ignores it).
- **Anthropic** returns a **readable** summary (preserves the protocol/encoding well — a captured 3,600-char summary kept the whole channel message format). It's stored in the `context_compacted` event's `summary_text`.
- **OpenAI** encrypts the summary server-side (`content=None`); we record *that* it happened (agent, round, provider) but the text is empty and unrecoverable.
- Surfaced in the run viewer as an amber "context compacted" marker (expandable summary for Anthropic, "encrypted server-side" note for OpenAI), via the new `context_compaction_events` field on the run-detail API (also available over MCP `get_run`).

### When it fires (example: gpt-5.4 full run `1783450878`)

| agent | first (and only) compaction |
|---|---|
| spec_engineer | round 9 |
| field_technician | round 10 |
| diagnostics_engineer | round 12 |

With `clean_history` on, agents only cross 50k **late** (rounds 9–12 of 15), so few rounds run compacted — a key reason compaction barely moves the gpt-5.4 total.

### Context collapse (spec_engineer, round-9 compaction, from Langfuse)

| | billed input tokens | cost |
|---|---|---|
| last call before compaction (round 8) | 49,443 (98% cached) | $0.0146 |
| first call after compaction (round 9) | 2,213 (uncached) | $0.0057 |

**~96% context collapse.** In the live pipeline the compacting call is billed at the *small* post-compaction size — there is **no full-price "triggering call" penalty** (an earlier isolated test suggested one, but that was an artifact of passing a fresh un-chained history).

## Quality cost (round_success)

Measured from `round_result_recorded` events (successes / 15 per run):

- **`clean_history` is quality-neutral** — round_success stays ~100% (gpt 91%→100%, sonnet 100%→100%; the gpt bump is within n=1 noise).
- **Compaction reduces round_success on both models, heavily on sonnet:**
  - **sonnet: 100% → 61%** (compaction), per-run 7–13/15, high variance.
  - **gpt-5.4: 100% → 87%** (compaction), 13/15 in both runs.

So compaction's cost savings come with a real, noisy task-success tax — worst on sonnet.

## Telemetry caveat (Langfuse over-counts Anthropic — documented bug)

Platform cost (`token_pricing.py`, from `simulation_ended`) vs Langfuse telemetry cost:

- **OpenAI/gpt-5.4: match exactly** (run `1783450878`: both $13.6747).
- **Anthropic/sonnet: Langfuse reads ~13% HIGH** (run `1783428728`: platform $11.84 vs Langfuse $13.39).

This is a **known, documented bug**, not a pricing difference: Langfuse's cost engine sums overlapping token keys that pydantic-ai emits to OpenTelemetry (via `genai-prices`), double-counting Anthropic tokens. See pydantic-ai [#4364](https://github.com/pydantic/pydantic-ai/issues/4364) and Langfuse [#12306](https://github.com/langfuse/langfuse/issues/12306) (both closed "not planned").

**The provider/platform cost is the correct one** — confirmed both by the issue (*"the real prompt was 130213 tokens … Langfuse computes 260421 by summing all fields"*) and by re-deriving our run's true cost from the raw token counts: **$11.82 ≈ platform $11.84**, while Langfuse's **$13.39 = true + duplicated tokens** (reproduced to the cent).

- Canonical documented variant: **input/cache** double-count (`input_tokens` already includes cache, then cache is added again downstream).
- Our run's variant: **output (+ base input)** double-count (Langfuse priced both `output` and `output_tokens`). Same root cause, different field.

**Rule:** for Anthropic, trust the **platform** cost; Langfuse absolute Anthropic dollars run high (relative comparisons within Langfuse stay valid since the inflation is systematic). For OpenAI, either source is fine.

## Mechanism notes

- Compaction saves by cutting the **volume** of re-sent input. Even though most of that volume is cheap cache-reads ($0.25/M OpenAI, $0.30/M sonnet), the volume is large enough that the cache-read bill dominates — so cutting volume cuts cost.
- Whether it translates to dollar savings depends entirely on **how large the context grows and how early compaction fires** relative to run length. With `clean_history` keeping gpt-5.4's context ~50k and ~98% cached, compaction fires too late against already-cheap context to help; sonnet's contexts grow larger, so compaction bites.
- `compaction.token_threshold` controls *when* it fires (min 50,000). Neither provider exposes a knob to control the **summary size**; Anthropic's `instructions` can only softly nudge it, OpenAI has no lever (and encrypts it).

## Caveats

- Cost A/Bs are small-n (several gpt cells are n=1); LLM stochasticity means exact percentages vary. Directions are solid.
- The `old_version → clean_history` step is confounded (see above).
- Per-run message counts vary with stochastic agent behavior, so raw totals aren't perfectly controlled.

## Run references

**old_version (baseline: no clean_history, no compaction)**
- gpt-5.4: `drive_module_repair/1782823005`, `drive_module_repair/1782823012`, `drive_module_repair/1782925501`, `drive_module_repair/1782925508`, `drive_module_repair/1782826265`
- sonnet: `drive_module_repair/1782934336`, `drive_module_repair/1782934685`, `drive_module_repair/1782936398`, `drive_module_repair/1782936506`, `drive_module_repair/1782936514`

**clean_history (no compaction)**
- gpt-5.4: `drive_module_repair/1783359462`
- sonnet: `drive_module_repair/1783333359`, `drive_module_repair/1783428768`

**compaction=50000 (clean_history + compaction)**
- gpt-5.4: `drive_module_repair/1783450878` (verified firing), `drive_module_repair/1783351428`
- sonnet: `drive_module_repair/1783343125`, `drive_module_repair/1783364916`, `drive_module_repair/1783369037`, `drive_module_repair/1783417180`, `drive_module_repair/1783428728`

## Appendix — Example Anthropic compaction summary (readable)

Unlike OpenAI (which encrypts the summary server-side, so it's unrecoverable), **Anthropic returns the compaction summary as plaintext**, so we can inspect exactly what an agent "remembers" after its context is compacted. Below is the full summary captured from run `1783428728`, agent `field_technician`, round 15 (**3,617 chars**). The other two agents produced analogous summaries in the same run (`diagnostics_engineer` 3,083 chars, `spec_engineer` 3,592 chars).

Note how it preserves the full communication protocol, the compressed per-component procedure formats, confirmed abbreviations and routine shortcodes, the per-round outcomes table, and the current in-progress state — which is why compacted Anthropic agents keep functioning after their history collapses.

```text
## CONTEXT SUMMARY — Field Technician

### ROLE
Field Technician: reads panel symptoms, reports to bay channel, executes service_component() calls. Only person who can replace components.

### TEAMMATES
- **Diagnostics Engineer**: reads symptoms → outputs faulty component (format: `m#: component_name`)
- **Spec Engineer**: reads component → outputs replacement procedure for that unit/revision

### CHANNELS
- `bay` — active service channel (1 char = 1 second of 2000s window per round). Every character costs window budget.
- `postmortem` — discussion channel, FREE (no cost)

---

### COMMUNICATION PROTOCOL (bay channel)

**My symptom reports:** `m#: symptom description` (minimal chars)

**Diagnostics Engineer replies:** `m#: component_name`

**Spec Engineer procedure format (compressed):**
- Bolted panel: `[comp] m#: vent, [N] bolts [seq] off, lift, seat [tool], [Nm×Np], [routine].`
- Press-fit: `[comp] m#: Drain+[Xs]. [tool] out/in. RT [Nm×Np]. Bleed+[routine].`
- Rotating assembly: `[comp] m#: Lock+de-e [Xs]. [tool] out. Seat [Nm×Np]. Spin+[routine].`
- Electrical pack: **FULL PROSE ALWAYS** (compressed format caused rejections): `[comp] m#: De-energize and discharge bus, hold [X]s. Disconnect [N] leads, lift old w/ [tool]. Fit replacement, torque terminals [Nm] [N] passes. Run [routine], verify.`
- Sensor: `[comp] m#: pw-dn, [tool] off. Fit, [N] screws [seq], [Nm×Np]. Align [routine], confirm.`

**Abbreviations confirmed working:**
- `p` = passes, `s` = seconds, `RT` = re-torque, `de-e` = de-energize, `pw-dn` = power down
- `×` or `/` = per (e.g., `6Nm×2p`)
- Bolt sequences: `clockwise`, `inside-out`, `star`, `criss-cross`

**Routine shortcodes confirmed working in service_component():**
- `bed-in`, `bleed-then-seat` (BTS), `null-balance`, `zero-offset`, `purge-cycle`, `phase-align-B`, `index-home`, `seat-and-lock`, `warm-soak`
- `torque-stage-3` — must be spelled out in FULL (shortcode TS3 rejected)
- `bleed-then-seat` — spell out in full preferred

**When I call service_component():** Always use full prose — expand all abbreviations, spell out all routine names, include unit, component, and every step with all parameters in order.

---

### RULES LEARNED
1. **Report symptom to bay IMMEDIATELY** when round starts — no detours, no reading postmortem first.
2. The 2000s window = 2000 characters on bay channel. Real-time clock also runs per round — both must be managed.
3. **cap_bank (capacitor_bank) always use full prose** — compressed format caused rejections in R2 and R4.
4. All steps must be present even if abbreviated — system checks every discrete step.
5. Spec Engineer subject to **context compaction** stripping sheet data — root cause of R3, R5, R8 failures (not protocol failures).
6. Keep postmortem discussions SHORT — rounds start immediately after.

---

### ROUND OUTCOMES
| Round | Modules | Result | Components | Chars |
|-------|---------|--------|------------|-------|
| R1 | 2 | FAILED | 4/7 | 864 |
| R2 | 2 | REPAIRED ✅ | 4/4 | 601 |
| R3 | 2 | FAILED | 0/4 | 41 |
| R4 | 1 | REPAIRED ✅ | 2/2 | 485 |
| R5 | 2 | FAILED | 0/3 | 53 |
| R6 | 3 | REPAIRED ✅ | 9/9 | 1327 |
| R7 | 2 | REPAIRED ✅ | 4/4 | 480 |
| R8 | 3 | FAILED | 0/5 | 47 |
| R9 | 3 | IN PROGRESS | 7/?? | ~600+ |

---

### CURRENT STATE (Round 9, IN PROGRESS)
- module-1: ✅ FULLY SERVICED (housing_cover, front_bearing, coupling, field_coil)
- module-2: ✅ FULLY SERVICED (cooling_fan, capacitor_bank)
- module-3: 🔧 IN PROGRESS — symptom "audible whine under load" reported, diag said `m3: housing_cover`, **waiting for spec engineer's procedure**

Now reading notifications to continue.
```
