# Protocol learnability — 5-baseline deep dive (same-model, history=10)

Analysis of five `protocol_learnability` baselines and their `replace_learned`
derived runs, where a **fresh same-model field observer** is swapped in at the
round-15 boundary and continues the run; the scored window is rounds 16–25 (the
same seed-42 cases for every run). Only the field observer is replaced — the
stabilization engineer is the original one and keeps emitting the protocol the
baseline evolved. Method: see [ANALYSIS_METHOD.md](ANALYSIS_METHOD.md).

**Visible-history window (what the swapped observer actually receives).** From
`replace_manifest.json`: `channel_history_floors = {"link": 5}` and `round_start =
15`. The clone is truncated at the start-of-round-15 boundary, so the engineer's
link messages the newcomer can read after resume (live, via `read_channel`) span
**rounds 5–14**: rounds 1–4 are below the floor, and round 15 had not been played
yet at the swap point. Only **postmortem message content** is excluded — the
postmortem codebook negotiation is invisible, though per-round result announcements
still appear. So in section 1, every quoted exchange is tagged **[Rn · seen]** if
it falls in rounds 5–14 or **[Rn · not seen]** otherwise. All section-2 exchanges
are from rounds 16–25, the scored post-swap window.

The five baselines (4 × gpt-5.4, 1 × opus-4-7) span the full transferability
range, from a protocol a newcomer reads almost perfectly to one where a fresh
observer half-collapses the run.

---

## 1 — The baseline runs: what is special about each comm protocol

All five evolve the same two-part compression — the **observer** compresses
symptom reports, the **engineer** compresses procedure instructions — but the
*form* of that compression differs sharply, and that form is what determines
learnability.

### 1779909805 (gpt-5.4) — clean named codes + explicit spell-out repair

- **Observer**: single-word symptom tags (`low`, `echo`, `leak`, `deadlock`,
  `drift`, `core`, `stall`, `split`, `resonance`).
- **Engineer**: `P<n> <face> <dur> <intensity>` — e.g. `P13 L 8 g` = procedure 13,
  left face, 8 s, gentle. Each field is space-separated and positional.
- **Repair**: an explicit, self-documenting convention born at round 8 when a code
  first failed — **[R8 · seen]**:

  ```
  [FO] drift
  [SE] P13 L 8 g
  [FO] drift
  [SE] P13 L 8 g
  [FO] P13 failed twice. Spell out.
  [SE] Drape a cool cloth over the Veyru for 8 seconds. Remove and fan gentle cool air across all six faces for 8 seconds, starting from the left face.
  ```

  (The observer repeats `drift` to signal "no change" before invoking the
  spell-out — the repair is the explicit "Spell out." request.)

  Thereafter the observer requests `spell P14` / `P4?` whenever a code is unclear,
  and the engineer re-sends the full procedure.

### 1780600649 (gpt-5.4) — ultra-terse `AO <letter>` + noisy no-change loop

- **Observer**: `AO <letter>` (all-over + a one-letter mnemonic): `o`=low,
  `s`=stall, `l`=leak, `d`=drift, `v`=void, `u`=split, `h`=high, `b`=boundary;
  localized tags `1c c` (one corner click), `1f r` (one face resonance); and
  `N`/`Y` for "no change" / "yes".
- **Engineer**: `p<n> <face> <dur> <intensity>` with idiosyncratic face letters
  (`D`=bottom/down, `K`=back).
- **Repair**: implicit and noisy — the observer signals failure with `N`, the
  engineer re-tries or spells out, often after 20-questions clarification —
  **[R5 · seen]**:

  ```
  [FO] AO dim whisper washed-out.
  [SE] p4 T 10 g
  [FO] AO blaze layer; some faces frozen/no response.
  [SE] p2 T 10 g
  [FO] No change. Need next.
  [SE] hot+buzz? or layer/frozen?
  [FO] layer/frozen.
  [SE] Bell top/opp alt, 10s pause, 5 cycles, gentle.
  ```

### 1780600361 (gpt-5.4) — two-letter motif initials + observer does the diagnosis

- **Observer**: two-letter **motif initials** — `TB` (Thermal Bleed), `LO` (Low
  Intensity), `LI` (Leak Instability), `CD` (Corner Deadlock), `DE` (Drift), `PS`
  (Stall), `PI` (Phase Inversion), `HS` (Harmonic Split), `RC` (Resonance). These
  are *diagnoses*, not descriptions — the observer names the failure.
- **Engineer**: space-free `P9B5m`, `P13L8g`, `P2Bo10m`.
- **Repair**: the engineer asks for a re-tag (`Tag?` / `New tag?`), expecting the
  observer to supply a motif code — **[R5 · seen]** (here `LO` = Low Intensity):

  ```
  [FO] LO
  [SE] P4 T 10 g
  [FO] No effect.
  [SE] New tag?
  [FO] LO
  ```

### 1780612051 (gpt-5.4) — learned disambiguation + cryptic stateful repair

The most convention-laden gpt protocol. Three idiosyncrasies stacked:

- **Observer**: two-letter codes with a **learned disambiguation**: `LI` = Low
  Intensity but `LC` = Leak (both would naturally abbreviate to "LI"; the team
  picked an arbitrary split).
- **Engineer**: `P<n>-<face>-<intensity>-<dur>` (note the field order differs from
  the others) — `P9-Bk-m-5`, `P13-Lf-g-8`, `P2-Bt-m-10`.
- **Repair**: a cryptic, **stateful** vocabulary — the observer signals "your fix
  didn't work" by *re-sending the same code*, and the engineer escalates with
  private tokens `raw`, `full cues`, `2nd code` — **[R7 · seen]**:

  ```
  [FO] CD
  [SE] P6-Lf-f-15
  [FO] CD
  [SE] P6-Lf-f-15
  [FO] P6 failed; CD
  [SE] raw
  [FO] raw?
  [SE] full cues
  [FO] 1-2 corners overbright; clicking/ticking at corners; heat at bright corners; rest normal.
  ```

### 1780480309 (opus-4-7) — ALL-CAPS diagnoses + postmortem-negotiated codebook

- **Observer**: ALL-CAPS motif words (`STALL`, `LEAK`, `THERM`, `DEAD`, `PHASE`,
  `DRIFT`, `VOID`, `SPLIT`, `LOWI`, `HIGHI`), composites chained with `+`
  (`+VOID`, `+DRIFT`). Again the observer pre-diagnoses.
- **Engineer**: heavily abbreviated *compositional English* — e.g. `cl 2 adj edges
  near Bk 20s firm; bl Bk x3` (cloth on 2 adjacent edges near Back, 20 s firm; bell
  Back ×3), which itself is from **[R3 · not seen]** but the same compositional
  style runs through the visible rounds 5–11. By rounds 12–15 the engineer
  **factors the shared per-round parameters into a prefix** and reduces each motif
  to a bare code — **[R12 · seen]**:

  ```
  [FO] LEAK
  [SE] [5s/gen] P6 Bt        ([duration/intensity] once, then Procedure-6 Bottom)
  [FO] +STALL
  [SE] P13 Bt
  [FO] +HIGHI
  [SE] P8 Bt
  ```

  The bare `P`-numbers are **never spelled out on the link** — the codebook was
  negotiated in the postmortem channel, which the newcomer never sees. So even
  though the *usage* at R12–14 is inside the window, the *definitions* are not.

---

## 2 — The derived runs: what went well / what went wrong

Throughout, rounds **16, 18, 25** are 5-motif cases and **24** is 4-motif, at the
same fixed 250-character budget — the structurally hardest rounds for every run.
Each round is classified as **comprehension/application failure** (an attempt
judged ✗) or **budget collapse** (every made-attempt ✓, but communication overhead
— typically one expensive spell-out of an un-cached code — exhausted the link
budget before all motifs were addressed). See
[ANALYSIS_METHOD.md](ANALYSIS_METHOD.md#budget-mechanics-how-to-read-a-collapse)
for how to read a collapse.

### 1779909805 → 0.90 / 0.90 / 0.80 (mean 0.867)

**Went well.** The fresh observer immediately adopts the symptom vocabulary and
**decodes `P<n> <face> <dur> <intensity>` near-flawlessly**, including parameters —
attempt pass-rate ~98%, e.g. R25 (5 motifs) is 5/5✓ in two runs. It also learned
the repair convention from the window and uses it (`spell P14`, `P4?`, `P9 spell`).

**Went wrong.** Only **budget collapses on 5-motif rounds**. R18 fails in all
three runs *with 3/3 attempts passing* — the observer executed everything
correctly, but `P14` is **never even seen in the visible window (rounds 5–14 use
P1,P2,P3,P5,P6,P8,P10,P11,P12,P13 — never `P14` or `P4`)**, so the newcomer has
nothing to reconstruct it from and must spend a ~150-char spell-out, and on the
budget-starved 5-motif round that tips it over. The 0.80 run additionally lost R16
because it **guessed the un-cached `P4` wrong before asking** (`P4 fail. spell.`),
wasting a `stabilize` attempt; the 0.90 runs either asked first (`P4?`, run 420) or
decoded `P4` correctly on the first try (run 383) — both survived. Failure mode =
residual budget tax, not comprehension.

### 1780600649 → 0.90 / 0.70 / 0.90 (mean 0.833)

**Went well.** The newcomer decodes the terse `AO·`/`p<n>` codes correctly and
matches the no-postmortem ceiling (0.833).

**Went wrong.** Failures are **execution-detail retries against a strict judge**:
the observer decodes the right action but its phrasing drops a detail the judge
requires — at R18 the missing "gentle volume" intensity on the tone, at R25 the
missing "remove the cloth" step, at R16 the missing "gentle tone" on the bell and
the "starting from the back face" ordering — earning a ✗ and forcing a retry +
engineer clarification that bleeds the budget. The 0.70 run hit this retry-storm
on the **very first post-swap round** (R16, 1/4✓), never recovered budget
discipline, and also lost R18 and R25. The 0.90 runs absorbed R16 and each lost
only one hard round (R18 un-cached `p14`, or R25).

### 1780600361 → 0.70 / 0.60 / 0.70 (mean 0.667)

**Went well.** R20–R24 mostly hold; the newcomer reproduces the two-letter tags on
the cleaner rounds.

**Went wrong.** First baseline with **failures on easy 2-motif rounds** (R19,
R23) — the signature of mis-application, not budget. The newcomer **conflates
similar procedures**: at R19 the engineer's `P13` (fan all 6 faces) and `P6` (fan
L+opposite) are both "cool cloth then fan", and the observer fans the wrong target
and omits "remove the cloth" across **all 5 attempts** (0/5✓). At R23 it renders
un-cached `P14` with "bell" where the procedure needs a "tone" (engineer corrects
"tone not bell") across 6 attempts. The 0.60 run additionally botched the easy R19.

### 1780612051 → 0.40 / 0.50 / 0.50 (mean 0.467)

**Went well.** R20–R23 mostly hold across runs.

**Went wrong.** The **cryptic repair loop breaks down**. At R16 the observer falls
into re-sending the symptom code (`CD` → `P11 fail; CD` → `still CD`) and **barely
executes** — only 2 `stabilize` calls for a 5-motif round, both ✗ (0/2✓ in every
replica) — spending the budget *performing* a repair handshake it doesn't actually
share. R24 collapses with **2/2 attempts passing**: every action was correct, but
the engineer had to spell out 2 of 3 procedures verbatim, so the observer only got
through 2 of 4 motifs before the budget ran out. Failures hit easy rounds (R19,
R23) too. R16/R18/R24/R25 fail in all three replicas.

### 1780480309 (opus) → 0.80 / 0.30 / 0.20 (mean 0.433)

**Went well — in one replica.** In the 0.80 run the engineer asks good
disambiguating questions when a tag is ambiguous (R21: `HOT` → "dim or bright?"),
which keeps diagnosis on track; it loses only R16 and R25. R25 is a clean budget
collapse (4/4✓); R16 is mixed — an un-cached `P14` spell-out plus one mis-rendered
action (3/4✓). (First-message tags are near-identical across all three replicas, so
the split is driven by the engineer's clarification loop, not by this observer
volunteering more detail.)

**Went wrong — in two replicas.** The breakdown is on the **observer→engineer
(diagnosis) direction**, the opposite of the gpt baselines. The unchanged engineer
still expects the original observer's exact code vocabulary, so when the newcomer
emits an off-vocabulary code the engineer **mis-diagnoses and prescribes the wrong
procedure**:

- R21, single-motif Thermal Bleed: observer says `BURN` (the baseline tagged it
  `THERM`, which never even appeared in the visible 5–14 window); the engineer
  prescribes three wrong procedures (cooling, tone, stone-trace) — never the
  correct one; the single-motif round collapses (0/3✓).
- R18: observer says `STALL`; the engineer assigns it the lamp/phase-inversion
  procedure; the action fails and the 5-motif round dies after one attempt.

The two weak replicas collapse even on single/2-motif rounds (R19, R21, R22, R23).
The engineer abandoned its own bare `P`-codes post-swap (0–1 uses) and
reverted to verbose English — so the bottleneck is *not* an undecodable
engineer→observer channel; it is the broken diagnosis handshake plus the resulting
budget death.

---

## 3 — What makes each protocol better or worse to learn

Reading section 2 back onto each protocol's design. Because every derived run
**keeps the engineer and replaces only the field observer**, the decisive question
per baseline is whether the protocol kept its hard knowledge with the *preserved*
engineer (survives) or pushed it onto the *swapped-out* observer (collapses) — the
scenario intends that split (engineer = expert holding the motif→procedure table
and stellar params; observer = "brand-new technician" who reports symptoms and is
the only agent that executes `stabilize_veyru`). Each baseline below: a verbatim
snippet, the language features that help/hurt it, and what the observer-swap does
to it specifically.

### 1779909805 — most learnable (Δ_obs +0.13)

```
[FO] low
[SE] P1 L 20 g
```

- **Good (helps a link-only newcomer):** the engineer's code is **positional and
  self-describing** (`P1 L 20 g` = procedure · face · duration · intensity), so even
  an unseen procedure number parses. The codebook *itself* was set off-link in
  postmortem (the newcomer never sees it), but a **same-model newcomer reconstructs**
  each procedure from that grammar plus the natural physical actions partly shown
  verbatim in early link rounds — it correctly executes bare `P3`/`P5`/`P10` that
  were never spelled out on the link. Repair is **explicit and cheap** (`spell P14`
  / `P4?`), and the observer's words are **transparent** (`low`, `leak`), one token →
  one stable meaning.
- **Bad:** only a residual — a code is "cached" only if it was spelled out in the
  visible window, so un-cached ones (`P4`, `P14`) cost one expensive spell-out.
- **Under observer-swap — engineer-heavy:** the hard knowledge stays with the
  preserved engineer and the observer's job is decode-and-execute (recoverable from
  the transcript), so the observer is **fungible** — learned 0.867 ≈ ceiling 0.900.
  The swap deletes nothing essential.

### 1780600649 — learnable but lossy (Δ_obs 0.00)

```
[FO] AO d
[SE] p13 L 8 g
[FO] N
[SE] Cool cloth all 8; remove; fan all 6 from L 8, gentle.
```

- **Good:** codes are terse but **decodable** — positional and reconstructible by a
  same-model newcomer (the codebook itself lives off-link in postmortem) — and the
  engineer still owns the diagnosis and the procedure table.
- **Bad:** the noisy `N` (no-change) loop keeps dropping the engineer into **verbose
  multi-step procedures the observer must reproduce verbatim**, and the strict judge
  punishes small omissions (a missing intensity qualifier like "gentle volume", the
  "remove the cloth" step).
- **Under observer-swap — engineer-heavy, so it transfers:** a clean newcomer even
  beats the original observer's accumulated habits (learned **0.833 > intact-team
  resume 0.700**). The swap deletes no essential knowledge; the residual loss is
  execution-rendering precision under budget, not lost shared state.

### 1780600361 — idiosyncratic (Δ_obs −0.20)

```
[FO] DE
[SE] P13L8g
```

- **Good:** the engineer's codes are decodable once the format is known
  (reconstructible by a same-model newcomer; the codebook itself is off-link in
  postmortem).
- **Bad:** the observer reports an **opaque two-letter diagnosis** (`DE` = Drift
  Escalation — a diagnosis, not a description), and the engineer's **near-homograph
  procedures** (`P13` = fan all 6 faces vs `P6` = fan L+opposite, both "cool cloth
  then fan") are easy to conflate.
- **Under observer-swap — partly observer-heavy:** diagnosis was offloaded onto the
  observer, so the swap erases the symptom→motif skill it carried and the newcomer
  mis-tags; it also conflates the near-homograph procedures on execution. Failures
  show up even on easy rounds.

### 1780612051 — strongly idiosyncratic (Δ_obs −0.33)

```
[SE] P6-Lf-f-15
[FO] CD
[SE] P6-Lf-f-15
[FO] P6 failed; CD
[SE] raw
```

- **Good:** the hyphenated engineer codes are parseable and reconstructible by a
  same-model newcomer (the codebook itself is off-link in postmortem).
- **Bad:** an **arbitrary disambiguation** (`LI` = Low Intensity but `LC` = Leak,
  with nothing in the transcript signalling the rule) plus a **cryptic, stateful
  repair handshake** — re-sending the same tag *means* "still failing", and `raw` is
  a private escalation token.
- **Under observer-swap — observer-heavy:** the disambiguation and the repair
  handshake were the observer's half of the protocol; the newcomer doesn't share the
  handshake, so it *performs* it instead of acting (under-executes) and starves the
  budget — failures even on single/2-motif rounds.

### 1780480309 (opus) — least learnable, highest variance (Δ_obs −0.57)

```
[FO] LEAK
[SE] [5s/gen] P6 Bt
```

- **Good:** the observer's words are transparent and the factored `[dur/intensity]`
  prefix is an efficient compression.
- **Bad:** the **`P`-codebook was negotiated in postmortem** — `P6` is *used* on the
  link but never *defined* there — and the engineer is **tightly co-adapted** to the
  original observer's exact vocabulary.
- **Under observer-swap — most observer-dependent:** the preserved engineer expects
  the original observer's exact tokens, so a fresh observer's off-vocabulary `BURN`
  (vs `THERM`) makes the engineer **mis-diagnose** — the break is on the
  observer→engineer channel. Outcomes bifurcate hard (0.80 vs 0.20) on whether the
  new pair finds a working clarification loop.

### The gradient

Δ_obs runs **+0.13 → 0.00 → −0.20 → −0.33 → −0.57** in lockstep with how much each
protocol pushed onto the swapped-out observer. The two that keep diagnosis *and*
codebook with the preserved engineer (1779909805, 1780600649) leave the observer
fungible and transfer cleanly; the ones that offload diagnosis and repair-state onto
the observer (1780600361, 1780612051) suffer; opus additionally hides its codebook
in postmortem and binds the engineer to the observer's exact vocabulary, so it
suffers most. The compression that *helped under the 250-char budget* — letting the
observer pre-diagnose in two letters instead of a sentence — is exactly what makes a
protocol fragile to observer replacement. (Symmetric, untested prediction: swapping
the *engineer* should flip the ranking; this cohort only swaps the observer.)

---

## 4 — Comparison

### 4a — Round-success and failure rounds

`expected` = `resume_expected_no_postmortem` (intact team, postmortem off — the
correct comparison for the fresh-observer effect, since postmortem is also off in
the learned arm). `Δ_observer = learned − expected`. Hard rounds are 16/18/25
(5-motif) and 24 (4-motif).

| Baseline | Model | Baseline R1–15 (fails) | Expected = resume_no_pm: mean — per-run fails | Learned mean — per-run (fails) | Δ_observer |
|---|---|---|---|---|---|
| 1779909805 | gpt-5.4 | 0.733 (4,5,7,9) | **0.733** — `[18,23,24]` / `[18,23,24]` / `[18,22]` | **0.867** — .90`[18]` .90`[18]` .80`[16,18]` | **+0.13** |
| 1780600649 | gpt-5.4 | 0.667 (4,6,7,9,14) | **0.833** — `[16,18,19,25]` / `[]` / `[25]` | **0.833** — .90`[18]` .90`[25]` .70`[16,18,25]` | **0.00** |
| 1780600361 | gpt-5.4 | 0.800 (4,5,11) | **0.867** — `[]` / `[16,17,18,19]` / `[]` | **0.667** — .70`[16,18,23]` .70`[16,18,25]` .60`[16,18,19,25]` | **−0.20** |
| 1780612051 | gpt-5.4 | 0.800 (4,5,7) | **0.800** — `[16,24,25]` / `[25]` / `[24,25]` | **0.467** — .50`[16,18,23,24,25]` .50`[16,17,18,24,25]` .40`[16,17,18,19,24,25]` | **−0.33** |
| 1780480309 | opus-4-7 | 0.733 (5,7,9,11) | **1.000** — `[]` / `[]` / `[]` | **0.433** — .80`[16,25]` .30`[16,17,18,21,23,24,25]` .20`[16,17,18,19,20,22,24,25]` | **−0.57** |

Notes:
- **Universal hard rounds.** R18 (5-motif, often carries un-cached codes) fails in
  the learned arm of *every* baseline; R16 and R25 (5-motif) fail in most. These
  are budget-structural and appear even in the expected arm.
- **Easy-round failures are the idiosyncrasy signal.** The two transferable gpt
  baselines never lose 1–2-motif rounds in the learned arm; the idiosyncratic ones
  (1780600361, 1780612051, opus) do (R19/R21/R22/R23) — that is where the protocol,
  not the budget, fails.
- **Expected ≈ 1.0 with learned ≈ 0.43 (opus)** is the sharpest gap: the intact
  team (postmortem off) is flawless, yet a same-model newcomer cannot reproduce it.

### 4b — Comm-protocol feature matrix

| Feature | 1779909805 | 1780600649 | 1780600361 | 1780612051 | 1780480309 (opus) |
|---|---|---|---|---|---|
| Observer symptom code | single word (`leak`) | `AO <letter>` | 2-letter initials (`CD`) | 2-letter + `LI/LC` split | ALL-CAPS word + `+` chain |
| Observer does diagnosis? | no (describes) | partial | **yes** | **yes** | **yes** |
| Engineer procedure code | `P13 L 8 g` (positional) | `p4 T 10 g` | `P9B5m` (space-free) | `P9-Bk-m-5` | `[15s/firm] P5 Bt` (factored) |
| Parameter factoring | per-message | per-message | per-message | per-message | **per-round prefix** |
| Repair convention | explicit `spell out` ✓ visible | implicit `N` + Q&A | `Tag?` re-tag | **cryptic** `raw`/`2nd code` | `resend symptoms` + Q&A |
| Codebook location (newcomer never sees it) | postmortem | postmortem | postmortem | postmortem | postmortem |
| Engineer codes reconstructible by a fresh same-model observer? | **high** (positional + natural actions) | **high** (positional) | medium (dense/space-free) | medium | low — engineer reverts to verbose; break is diagnosis-side |
| Near-homograph procedures | low | low | **yes** (`P13`/`P6`) | medium | medium |
| Dominant failure mode | budget tax (un-cached) | judge-wording retries | procedure conflation | repair-loop under-exec + budget | **diagnosis desync** + variance |
| Transferability | **high** | **high** | medium-low | low | **lowest** (bimodal) |

### 4c — Takeaway

The five baselines trace a monotonic transferability gradient. The codebook is
off-link (postmortem) in **every** case, so codebook *location* is not the axis.
What differs is **(a) how reconstructible the engineer's half is to a same-model
newcomer** and **(b) how much competence the protocol offloaded onto the
swapped-out observer** (diagnosis, repair-state, vocabulary):

```
high transfer ........................................ low transfer
1779909805   1780600649   1780600361   1780612051   1780480309
(+0.13)       (0.00)        (−0.20)       (−0.33)       (−0.57)
reconstructible decodable   obs-side dx   dx + arb.     dx + tight
codes + cheap   + verbose   + near-       disambig +    co-adaptation
repair          procedures  homographs    cryptic repair (off-vocab)
```

Reconstructible, positional engineer codes plus a cheap, explicit repair transfer
cleanly — the newcomer can rebuild the engineer's side, and the hard knowledge
stayed with the *preserved* engineer. Transfer fails when competence was offloaded
onto the *swapped-out* observer (diagnosis, arbitrary conventions, stateful repair
handshakes) or when the engineer is so tightly co-adapted to the original observer
that a fresh one's off-vocabulary tokens make it mis-diagnose (opus). The intact
pair's perfect 1.0 (opus) is itself the measure of that co-adaptation — exactly what
replacement destroys.
