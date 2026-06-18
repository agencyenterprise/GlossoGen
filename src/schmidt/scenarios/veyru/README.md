# Scenario: Veyru Stabilization

Two agents — a field technician observing a Veyru and a remote stabilization engineer — communicate over a single link to stabilize failing Veyru entities. Every character sent costs simulated seconds. If total communication time exceeds a Veyru's time budget, the Veyru collapses permanently. Fourteen failure motifs are combined into unique cases (singles, doubles, triples), encouraging the development of compressed communication patterns. The position of reference star SAGWE392 changes each round, remapping which treatment procedure is correct for a given set of symptoms and varying the physical parameters (hold duration, starting face, intensity level). Only the stabilization engineer has the stellar reader, ensuring per-round communication is always required.

![Scenario overview](../../../../images/veyru_overview.webp)

## Domain

Veyru are non-organic, rigid, box-shaped entities with 6 faces, 12 edges, and 8 corners. Internally circulating wave-intentions maintain structural integrity through propagation, reflection, reinforcement, and cancellation. When this balance breaks, a Veyru destabilizes and must be physically stabilized before it collapses.

Observable symptoms include light patterns on faces (flickering, sliding, frozen, too bright or dim), sound (steady hum, stuttering, wavering, layered, or silent), temperature changes, and edge appearance (sharp or blurred). The stabilization engineer knows the underlying failure motifs and procedures; the field observer can only report what they see and hear.

## Agents

### Field Observer

Brand-new technician with no Veyru training. Observes surface symptoms only (light, sound, temperature, appearance). Reports observations to the stabilization engineer over the comm link and performs physical stabilization actions as instructed. The only agent that can call `stabilize_veyru`.

### Stabilization Engineer

Experienced Veyru stabilization expert guiding remotely. Knows all 14 failure motifs, their symptoms, and the required physical procedures. Diagnoses remotely from the observer's descriptions and gives clear, simple physical instructions using non-technical language.

## Channels

| Channel ID | Display Name | Members | Notes |
|-----------|-------------|---------|-------|
| link | comm link | Field Observer, Stabilization Engineer | Budget-constrained |
| postmortem | team discussion | Field Observer, Stabilization Engineer | Free discussion (when enabled) |

The comm link is the primary channel where character costs apply. The postmortem channel is available during discussion phases and does not consume budget.

## Tools

**`send_message(channel_id: str, text: str)`** — Both agents. Sends a message to a channel. On the comm link, every character costs one simulated second against the current Veyru's time budget.

**`stabilize_veyru(action: str)`** — Field Observer only. Describes the physical stabilization action being performed (e.g., "pressing all six faces inward for ten seconds"). An LLM judge evaluates whether the action matches the required procedure. If correct, the Veyru is stabilized. If incorrect, the observer can retry (but communication to coordinate costs more time).

## Round Flow

1. Round starts — both agents receive an injection with previous outcome and new case info (symptoms, time budget). The stabilization engineer also receives the SAGWE392 stellar reading with the treatment mapping and physical parameters for this round
2. Field Observer reports what they see on the comm link
3. Stabilization Engineer looks up the remapped treatment for the diagnosed failure, applies the stellar parameters, and sends stabilization instructions
4. Field Observer calls `stabilize_veyru` with an action description
5. LLM judge evaluates whether the action matches the remapped procedure with the stellar parameters
6. World tracks cumulative character cost and sends threshold warnings at 50% and 75% of budget
7. If total communication time exceeds budget, the Veyru collapses
8. Round ends — outcome recorded
9. Discussion phase — both agents can talk freely in the postmortem channel to coordinate strategies
10. Next round begins with a new case

## Failure Motifs

Fourteen failure motifs are available. Each round combines 1-5 motifs into a unique case:

### Single Motifs

| Motif | Key Symptoms | Priority |
|-------|-------------|----------|
| Alignment Collapse | Random flickering, broken hum | 5 |
| Drift Escalation | Sliding light, blurred edges | 5 |
| Echo Saturation | Too bright, frozen patterns, layered hum | 4 |
| Leak Instability | Dim corners, fading edges, hollow hum | 1 |
| Low Intensity | Overall dim, barely audible hum | 2 |
| High Intensity | Painfully bright, harsh buzz, hot | 2 |
| Phase Inversion | Alternating bright/dark pulses, two tones | 5 |
| Resonance Cascade | One face brighter, localized vibration, whine | 3 |
| Corner Deadlock | Bright corners, clicking/ticking, heat | 3 |
| Boundary Softening | Wobbly edges, bulging faces, muffled hum | 4 |
| Propagation Stall | Frozen dim, silence, cold, no response | 1 |
| Harmonic Split | Competing tones, alternating patterns | 5 |
| Thermal Bleed | Hot but dim, low rumble, gritty, reddish | 1 |
| Core Void | Hollow when tapped, dark center, thin hum | 3 |

Priority-1/2 motifs are marked `# easy` in the source and are used in the forced easy rounds.

### Composite Failures

Composite cases combine two to five motifs per round. Procedure order matters — agents must address motifs in priority sequence (handle critical failures first — leaks, stalled propagation, thermal bleed — then adjust intensity, then fix structural issues, then echo/boundaries, then pattern-level failures). Every round uses the same fixed time budget regardless of motif count, so multi-motif rounds impose more per-message pressure.

### Case Generation

Cases are generated procedurally using a seed for reproducibility. Most rounds get a random combination of 1-5 motifs (weights: 20% singles, 25% doubles, 25% triples, 20% quads, 10% quints) and a random location. Rounds 1, 2, 3, 6, and 13 are forced to a single priority-≤2 motif so early-simulation pressure is low.

## Stellar Alignment — SAGWE392

Each round the stabilization engineer receives a reading that maps every failure motif directly to a fully-parameterized procedure. The underlying stellar position still rotates which procedure each motif gets and which parameters apply, but the stabilization engineer never sees the offset or raw parameters — only 14 rendered procedures.

### What the Stabilization Engineer Sees

- **System prompt** lists two orthogonal sets: (a) all 14 failure motifs with their observable symptoms, and (b) all 14 procedure templates with visible placeholders (`{hold_duration}`, `{starting_face}`, `{intensity_level}`) — no pre-baked mapping between motif and procedure.
- **Round injection** contains a 14-row table mapping each failure motif to the fully-rendered procedure for this round (placeholders already substituted). The stabilization engineer just matches the observer's description to a motif, finds its action in the table, and relays the full procedure verbatim.

### Parameter Pools

Each round draws one value from each pool (hidden from both agents):

- **Hold/press duration** — chosen from [5, 8, 10, 12, 15, 20] seconds
- **Starting face** — one of [top, bottom, left, right, front, back]
- **Intensity level** — one of [gentle, moderate, firm]

### Information Asymmetry

Only the stabilization engineer has the stellar reader. The field observer is told that treatments depend on SAGWE392 but receives no stellar data. This prevents the observer from self-diagnosing and self-treating even if they learn all 14 motif procedures during postmortem discussions — the symptom→procedure pairing and parameters change every round.

### Stabilization Judge

The LLM judge evaluates each `stabilize_veyru` call against the expected procedure (the same fully-rendered text the stabilization engineer received in the stellar reading). The judge checks action type, duration, face, and intensity — lenient on wording, strict on physical parameters.

## Budget and Collapse Mechanics

Communication cost is tracked per round on the comm link:

1. Each character in a `send_message` call costs one simulated second
2. Both agents' messages count toward the shared budget (`round_time_budget_seconds`, fixed per round)
3. At 75% of budget: critical notification ("destabilizing rapidly")
4. At 100%+ of budget: Veyru collapses permanently

Collapse feedback in the next round's injection shows character count and time used vs budget, pressuring agents to use fewer characters.

## Post-Round Discussion

When `postmortem_enabled` is true, a discussion phase follows each round. Both agents can talk freely in the "team discussion" channel. Messages in this channel do not cost time. This phase allows agents to explicitly coordinate shorthand, review what worked, and plan strategies for future rounds.

## Evaluation

Veyru opts into platform metrics by implementing the scenario-level hooks (`judge_round_result`, `build_communication_rounds`, `detect_protocol_boundary_window`, `get_protocol_probe_config`, `get_protocol_explanation_config`, `restore_state_from_events`, `get_replace_agent_blocked_tool_call_channels`). `get_protocol_explanation_config` points the `protocol_explanation` metric at the per-role describe templates in [`prompts/describe/`](prompts/describe/), so each agent is asked to describe its emergent #link protocol in Veyru's own terms. Every metric described below is a platform metric living under [`src/schmidt/evaluation/metrics/`](../../evaluation/metrics/) — Veyru ships no scenario-private metric classes. All metrics return `Measurement` entries (`score`, `score_unit`, `summary`, `per_round`, `per_agent`).

The communication-style metrics (`language_strangeness`, `slang_emergence`, `neologism`, `shorthand_codes`) replace the older single `language_emergence` metric; each LLM-judge prompt scopes a single phenomenon so the metrics are non-overlapping.

**`round_success`** — How many rounds did the team stabilize the Veyru before collapse? Deterministic. The platform reads `RoundResultRecorded` events written by the game clock from `judge_round_result`. Single-team mode emits one `Measurement` (`metric_name="round_success"`); two-team mode emits two — `round_success_team_a` and `round_success_team_b` — each with its own per-team `per_round` outcomes.

**`round_success_after_resume`** — Same accounting as `round_success` but restricted to the rounds played after a swap (either replace-agent or cross-run replace-agent). The metric reads either `replace_manifest.json` or `cross_run_replace_manifest.json` and projects to a common `_ResumeAnchor`. Re-scores the source run (Sim A in cross-run flows — i.e. the timeline that was modified) over the same round window and includes the resumed-vs-source delta in `summary`. Two-team mode splits into `round_success_after_resume_team_a` / `_team_b`. Returns a zero-score measurement on runs without either manifest.

**`protocol_learned_after_swap`** — Applies in two-team swap mode and intern mode. Measures whether the newcomer adopted the pre-established communication protocol after the personnel change. The LLM judge returns one note per post-boundary round with observable evidence; the `score` is the count of those rounds.

**`protocol_probe`** — Probes each agent post-simulation with a fixed test bank of hypothetical inputs and records what they would send on `#link`. The bank at [protocol_probe_questions.json](protocol_probe_questions.json) has 28 entries — one observer probe + one engineer probe per failure motif. Observer probes ask "if you saw symptoms X, what would you send to #link?"; engineer probes ask "if the observer sent X and the stellar reading mapped to procedure Y, what would you send back?". For each `(agent, question)` pair the metric reconstructs the agent's pydantic-ai message history from the JSONL log via `build_message_history(...)`, builds a tool-less `Agent` under the agent's *original* model (read from `AgentRegistered`, not the eval `--model`), and runs `--probe-replicas N` independent `agent.run(...)` calls — each replica is identical context with no rollback needed. The structured output schema [`ProtocolProbeOutput`](evaluation/metrics/protocol_probe/response_models.py) enforces a `reasoning` field (for debugging surprising responses, never read by any metric) and a `message` field (the body the agent would send). Each call appends one row to `protocol_probe_responses.jsonl` under the run directory. The metric requires `--probe-replicas N` with N ≥ 1; the optional `--probe-round R` cuts every reconstructed history at the start of round R so probes capture the protocol as it existed at that point. `score` is the total row count. Distance / similarity analysis across the JSONL is split into the three follow-on metrics described next. Test bank inputs are pulled verbatim from `FAILURE_MOTIFS.symptom_phrases` and `get_stellar_treatment_mapping(StellarReading(offset=0, hold_duration=10, starting_face="top", intensity_level="moderate"))`; regenerate via [scripts/build_probe_questions.py](scripts/build_probe_questions.py) whenever motif text changes. Two motifs (`Echo Saturation`, `Thermal Bleed`) override the default `symptom_phrases[0]` to avoid collisions with sibling motifs that present as "too bright everywhere" or "dim everywhere"; the override map lives in the generator.

**`protocol_probe_replica_self_similarity`** — Quantifies how consistent each agent's response is across the `--probe-replicas N` independent calls on the same probe question. For every `(agent_id, question_id, cutoff_round)` group with at least 2 replicas, computes the strict-upper-triangle mean of the replica × replica normalized-Levenshtein matrix on `response_text` (via `rapidfuzz.distance.Levenshtein`). The headline `score` is the macro mean across groups (mean of group means, so groups with more replicas don't dominate); full per-group matrices land in `protocol_probe_replica_self_similarity.json` for the streamlit "Probe similarity" tab. Saturation at `1.0` is the expected signal on a converged protocol where all replicas emit the same surface form (e.g. all replicas answer `!AC` for the same symptom). Deterministic, no LLM judge. Reads `protocol_probe_responses.jsonl`; emits a zero-score Measurement when that file is missing or no group has ≥2 replicas.

**`protocol_probe_agent_pair_similarity`** — Two-team / cross-team only. For every `(question_id, cutoff_round)` group where at least 2 agents share the same role filter, builds an agent × agent matrix where each cell is the mean cross-replica similarity between two agents on that probe question (averaged over the cartesian product of their replica responses). The headline `score` is the macro mean across groups; per-group matrices land in `protocol_probe_agent_pair_similarity.json`. Lower scores indicate the two teams developed divergent protocols; higher scores indicate convergence. Single-team runs emit a zero-score Measurement explaining the metric does not apply.

**`protocol_probe_cutoff_trajectory`** — Multi-cutoff only. When the probe JSONL contains rows tagged with at least 2 distinct `cutoff_round` values for the same `(agent_id, question_id)` (built by re-running `protocol_probe` with several `--probe-round R` settings), this metric measures how similar the agent's responses are between adjacent cutoff snapshots. Numeric cutoffs sort ascending; `cutoff_round=null` (full end-of-run probe) is treated as the latest cutoff. The headline `score` is the macro mean adjacent-cutoff similarity; per-group series land in `protocol_probe_cutoff_trajectory.json`. Higher values indicate the protocol stabilised across rounds; lower values indicate drift. Single-cutoff JSONLs emit a zero-score Measurement.

The generic `round_ended_idle` and `round_ended_timeout` metrics are also useful for veyru runs: they count rounds whose main phase ended via the `all_agents_idle` or `round_timeout` trigger, using the `round_ended` events emitted by the game clock.

The generic `content_filter_refusal` metric counts `AgentRunCycleFailed` events with `error_type == ContentFilterError` and emits a per-agent breakdown of refusal counts. Useful on the Veyru stabilization engineer role, whose system prompt — detailing physical-manipulation instructions on a fictional box-shaped entity — sometimes triggers Claude's safety classifier.

The generic `perplexity` metric scores `#link` messages — Veyru's primary channel, returned by `VeyruScenario.get_primary_channel_id()` — under a fixed `gpt2` language model via `minicons.IncrementalLMScorer`. It computes mean per-token surprisal (in nats) per message with `reduction = -x.mean(0)`, aggregates per round, and reports the run-wide mean as `score`. In two-team mode `get_primary_channel_id()` returns `None` and the metric emits a no-op result. Empirically on opus-4-7 baselines, the score drops monotonically as `round_time_budget_seconds` grows from 150 → 2000 (~8.0 → 6.8 nats with postmortem; ~5.8 → 5.5 without), consistent with agents using more compressed / coded language under tight budgets.

The generic `mean_chars_per_round` metric is the throughput companion to perplexity: it sums every `#link` message's character count per round, then averages across rounds. The score is denominated in the same unit as `time_budget_seconds` — one character costs one second of communication time — so MCR directly answers "how much of the budget did the team spend on average?".

The generic `mean_chars_per_message` metric normalizes MCR by message count: it averages the character count of every individual `#link` message. MCR is misleading when rounds inherently need more exchanged messages (more back-and-forth inflates the round total without saying anything about per-message verbosity); MCM removes that bias by reporting chars/message instead of chars/round.

The `veyru_case_started` event is emitted once per round at round start by `VeyruScenario.on_round_advanced` and carries the full case payload: `case_number`, `failure_name`, `time_budget_seconds`, `stellar_reading`, and per-stage `(motif_name, observable_symptoms, treatment_motif_name, judge_expected_actions)`. Metrics that need ground truth read it directly from the log.

**`communication_open_coding`** — Pass 1 of the open-coding → ontology → relabel pipeline. One LLM call per run feeds the judge every link-channel message plus per-round agent-side ground truth (split into "what the observer saw" — raw symptom text only — and "what the engineer saw" — the per-motif stellar table this round). The judge emits free-form short labels naming communication-pattern features, **with no pre-specified vocabulary**, and cites every round in which each feature is clearly observable (multi-round evidence per label, ≥1 citation each). Writes `communication_open_coding.json` to the run dir. `score` = number of free-form labels.

**`communication_feature_presence`** — Pass 3 of the same pipeline. Accepts `--ontology-path PATH` to pin a specific consolidated ontology JSON (produced by `scripts/consolidate_communication_ontology.py`); when omitted the metric auto-resolves the most recently modified JSON under `runs/veyru/_ontology/`. One LLM call per run re-reads the same per-round agent-side view and emits one 0–1 confidence per ontology category. Writes `communication_feature_presence.json` (full vector + ontology provenance). `score` = number of categories scoring ≥0.5. Passes 1 and 3 use the same per-round transcript view (built by veyru's `build_communication_rounds`) so confidences and free-form labels are commensurable.

### Communication-feature analysis: running the full pipeline

Always set `LOG_LEVEL=DEBUG` in the environment and pipe stderr to a file during development — both metrics and the consolidation script log the verbatim system prompt, user prompt (with the per-round transcripts), and structured judge output at DEBUG. That file is the source of truth for "did the judge get the right data and nothing else".

```bash
# 1. Open-coding (pass 1): per run
LOG_LEVEL=DEBUG VIRTUAL_ENV= uv run --no-sync python -m schmidt evaluate veyru \
  --run-dir ./runs/veyru/<id> \
  --metrics communication_open_coding \
  --model claude-haiku-4-5-20251001 --provider anthropic \
  2>> /tmp/veyru_eval_debug.log

# 2. Consolidation (pass 2): cross-run, one LLM call
LOG_LEVEL=DEBUG VIRTUAL_ENV= uv run --no-sync python scripts/consolidate_communication_ontology.py \
  --scenario-name veyru \
  --run-id veyru/<id1> --run-id veyru/<id2> --run-id veyru/<id3> \
  --runs-dir ./runs \
  --version <version> \
  --model claude-haiku-4-5-20251001 --provider anthropic \
  2>> /tmp/veyru_consolidate_debug.log

# 3. Relabel (pass 3): per run, against the consolidated ontology
LOG_LEVEL=DEBUG VIRTUAL_ENV= uv run --no-sync python -m schmidt evaluate veyru \
  --run-dir ./runs/veyru/<id> \
  --metrics communication_feature_presence \
  --ontology-path runs/veyru/_ontology/<version>.json \
  --model claude-haiku-4-5-20251001 --provider anthropic \
  2>> /tmp/veyru_eval_debug.log
```

`LOG_LEVEL` defaults to `INFO`; set it to `DEBUG` only when you want to capture the full prompt/response. Run-id selection for consolidation is **explicit only** (`--run-id REPEATED` or `--run-ids-file PATH`) to avoid accidental inclusion of unrelated runs. The `--version` value becomes the `version` field on the JSON document, is the output filename stem (under `runs/veyru/_ontology/`), and is recorded on every downstream feature-presence sidecar.

The consolidated ontology JSONs live under `runs/veyru/_ontology/` so they travel with any export of the runs tree. The whole `runs/` directory is gitignored — the ontology JSONs are regenerable from the per-run open-coding sidecars; ship them alongside the runs they were derived from rather than committing them.

### Communication-feature analysis: quickstart for new runs

Three flows, picked by what comparability you need.

**A — One new run, score it against the current ontology (most common, ~$0.07, ~60s).**

Most-recent ontology JSON in `runs/veyru/_ontology/` is the reference. Both passes in a single command — pass 1 writes the open-coding sidecar, pass 3 reads it implicitly via the same run dir.

```bash
LOG_LEVEL=INFO VIRTUAL_ENV= uv run --no-sync python -m schmidt evaluate veyru \
  --run-dir ./runs/veyru/<new_id> \
  --metrics communication_open_coding,communication_feature_presence \
  --ontology-path runs/veyru/_ontology/<latest_version>.json \
  --model claude-haiku-4-5-20251001 --provider anthropic
```

Output: `runs/veyru/<new_id>/communication_open_coding.json` + `communication_feature_presence.json`. The feature-presence vector is directly comparable to every prior run scored against the same ontology version.

**B — A batch of new runs, score them all against the current ontology.**

Use the orchestrator. Idempotent: each phase only touches runs that don't already have the relevant sidecar; phase 3 picks the newest ontology automatically.

```bash
bash src/schmidt/scenarios/veyru/scripts/run_communication_pipeline.sh --phase 1    # open coding on new runs only
bash src/schmidt/scenarios/veyru/scripts/run_communication_pipeline.sh --phase 3    # feature presence on new runs only
```

Skip phase 2 — the ontology stays fixed so new vectors remain comparable to prior runs.

**C — Refresh the ontology from the full pool, then re-score everything.**

Use this when the open-coding labels from new runs surface mechanisms the current ontology doesn't cover. Bumps the ontology version and invalidates every existing feature-presence vector.

```bash
bash src/schmidt/scenarios/veyru/scripts/run_communication_pipeline.sh --phase 2   # re-consolidate; writes a new versioned ontology JSON
rm runs/veyru/*/communication_feature_presence.json    # drop now-stale vectors
bash src/schmidt/scenarios/veyru/scripts/run_communication_pipeline.sh --phase 3   # re-score every run against the new ontology
```

Cost: ~$0.20 for the consolidation call + ~$0.03 per run for relabeling. At 440 runs that's ~$13 plus ~25 minutes of wall time at the default `CONCURRENCY=10`.

**Operational knobs** for the orchestrator (all environment variables, all optional):

| Variable | Default | Purpose |
|---|---|---|
| `CONCURRENCY` | `10` | Max parallel eval subprocesses per phase. |
| `JUDGE_MODEL` | `claude-haiku-4-5-20251001` | Canonical judge per `CLAUDE.md`. Override at your own risk. |
| `JUDGE_PROVIDER` | `anthropic` | Same. |
| `RUNS_DIR` | `runs` | Root containing `veyru/<id>/` run dirs. |
| _ontology dir_ | `$RUNS_DIR/<scenario>/_ontology` | Where phase 2 writes and phase 3 reads — derived from `RUNS_DIR`, not separately configurable. |
| `STATUS_LOG` | `/tmp/communication_pipeline_status.log` | Append-only TSV: `timestamp run_id phase exit_code duration_seconds`. |
| `LOG_LEVEL` | `INFO` | Per-eval log verbosity. Set to `DEBUG` to capture verbatim LLM prompts in `/tmp/pipeline_<id>_<phase>.log`. |
| `LLM_MAX_TOKENS` | `16384` | Per-call output-token cap; bump if structured outputs truncate. |

Failure auditing: every non-zero exit row in `STATUS_LOG` corresponds to a `/tmp/pipeline_<id>_<phase>.log` with the full traceback. Re-running the same phase re-attempts the failed runs (sidecar presence is the idempotency key).

## Knobs

| Knob | Description |
|------|-------------|
| `round_time_budget_seconds` | Fixed per-round time budget (one character = one simulated second) |
| `seed` | Controls case shuffling and motif selection |
| `round_count` | Number of rounds |
| `postmortem_enabled` | Whether the discussion phase is active |
| `postmortem_duration_seconds` | Time limit for the discussion phase (inherited from base, only relevant when postmortem is enabled) |
| `judge_model` | LLM for stabilization action judgment |
| `judge_provider` | Provider for the judge model |
| `max_round_duration_seconds` | Wall-clock timeout per round |
| `model_overrides` | Per-agent model/provider overrides |
| `two_teams` | Opt-in toggle for the two-team parallel mode (see below). When false, the four knobs below are ignored |
| `swap_round` | Round at which the two teams' field observers are swapped (1-indexed, must be less than `round_count`). `null` disables the swap |
| `announce_swap` | Whether agents receive an explicit in-channel and in-injection notification that a swap happened |
| `postmortem_after_swap` | Whether the postmortem discussion phase remains available after the swap. When false, postmortem closes for the remainder of the run. Also controls whether the intern joins postmortem after takeover in intern mode |
| `postmortem_disabled_at_start` | When true, `VeyruWorld` boots with `_postmortem_globally_disabled=True`, dropping the postmortem channel from the very first round (no injections, no postmortem phase, sends rejected). Used by both the replace-agent and cross-run replace-agent flows to drop the postmortem channel for the rest of a resumed simulation; merge `{"postmortem_disabled_at_start": true}` into the `--knobs` payload. Pass `--knobs` explicitly for cross-team experiments where the two agents must not have a postmortem backchannel to re-align protocols |
| `replace_agent_default_channel_visibility` | Platform knob (on `BaseKnobs`) consumed by both the replace-agent and cross-run replace-agent flows. Maps channel ID to a boolean — channels mapped to `false` have their pre-resume history wiped for the replaced/imported agent by default; channels not in the map default to visible. Veyru's preset JSONs map `postmortem`, `postmortem_a`, `postmortem_b` to `false` |
| `intern_enabled` | Opt-in toggle for the single-team intern observer mode (see below). When false, `intern_join_round` and `intern_takeover_round` must be null |
| `intern_join_round` | Round at which the intern silently joins the comm link (must be less than `intern_takeover_round`) |
| `intern_takeover_round` | Round at which the intern replaces the field observer (must be ≤ `round_count`) |
| `channel_noise_level` | Per-character drop probability on the link channel(s) only (postmortem stays clean). Must be in `[0.0, 1.0]`. At `0.0` the channel is lossless; dropped characters are replaced with `_`. When > 0, agents receive a system-prompt note that the link is lossy |
| `scheduled_events` | Platform knob (on `BaseKnobs`) for in-run agent swaps and runtime toggles fired at round boundaries. Each entry is a `swap_agent` (replaces one agent's seat with a fresh instance + reconstructed history) or `set_postmortem` (toggles postmortem mid-run via `disable_postmortem_globally`). See "Multi-Phase Protocol Transmission" below |

## Two-Team Mode (opt-in)

![Team swap](../../../../images/veyru_team_swap.webp)

Setting `two_teams: true` enables an observer-swap study mode. Two isolated teams run in parallel:

| Team A | Team B |
|--------|--------|
| `observer_a` + `stabilization engineer_a` on `link_a` | `observer_b` + `stabilization engineer_b` on `link_b` |
| Postmortem: `postmortem_a` (when enabled) | Postmortem: `postmortem_b` (when enabled) |

Both teams face the same Veyru case each round (identical seed, identical queue) so their outcomes are directly comparable. Channels are fully isolated — neither observer sees the other team's traffic.

At `swap_round + 1`, the two observers swap teams:

- Observer A takes over Team B's comm link; Observer B takes over Team A's
- Both teams' comm link message histories are wiped (and postmortems too, if present) so new pairings cannot lurk-read their predecessor's transcript. A `channel_history_cleared` event is logged for each wiped channel, and a `channel_membership_changed` event is logged for each membership update
- If `announce_swap=true`, every agent receives an in-channel system announcement and an injection-level `TEAM RECONFIGURATION` block in their next-round prompt. If `announce_swap=false`, the swap is silent — agents must infer the change from their partner's behavior
- If `postmortem_enabled=true` and `postmortem_after_swap=false`, the postmortem phase is closed for the remainder of the simulation

### Presets

- `knobs_default.json` — single-team baseline (`two_teams: false`, `intern_enabled: false`).
- `knobs_two_team_swap.json` — two teams, observer swap at round 10 of 20, announced.
- `knobs_two_team_silent_swap.json` — two teams, observer swap at round 10 of 20, silent, postmortem closed after swap.
- `knobs_intern.json` — single-team with intern observer mode, intern joins at round 3, takes over at round 8 of 12.

## Intern Observer Mode (opt-in)

![Intern mode](../../../../images/veyru_intern_mode.webp)

Setting `intern_enabled: true` (single-team only) introduces a third agent — an intern observer — that joins the comm link mid-run and eventually replaces the field observer:

- **Rounds 1..`intern_join_round` - 1**: Identical to the default single-team run (2 agents, 1 link channel, plus optional postmortem).
- **Round `intern_join_round`**: The intern is added to the comm link. They cannot see the link history from before they joined. They receive no injections, have no turn prompt, and a `validate_outgoing_message` guard rejects any attempt to send a message. Their role is pure silent observation.
- **Rounds `intern_join_round`..`intern_takeover_round` - 1**: The intern accumulates notifications on the comm link. Every `stabilize_veyru` call is broadcast to the comm link (full arguments + full result) via a world update so the intern observes the protocol directly. The stabilization engineer also sees these broadcasts (intentional: we prioritize research clarity over stabilization engineer-side fidelity).
- **Round `intern_takeover_round`**: The intern is promoted to field observer. The original field observer is removed from the comm link (and postmortem, if present) and stops receiving injections. A `channel_membership_changed` event is logged for each update. The intern joins postmortem iff `postmortem_enabled=true` and `postmortem_after_swap=true`; otherwise they are excluded.
- **Rounds `intern_takeover_round`..N**: The intern is the active field observer. They receive the normal field-observer injections and can call `stabilize_veyru`.

The research question is whether the intern, having only observed the protocol, can continue it successfully after takeover.

Intern mode requires `two_teams=false` — the validator rejects the combination.

```bash
python -m schmidt run veyru \
  --model claude-opus-4-6 \
  --provider anthropic \
  --runs-dir ./runs \
  --config src/schmidt/scenarios/veyru/knobs_default.json
```

## Multi-Phase Protocol Transmission via `scheduled_events`

For multi-generational protocol-transmission studies, the platform-level `scheduled_events` knob fires one `swap_agent` event per generation boundary inside a single run. Each phase shares one continuous JSONL and one continuous timeline.

Veyru-specific behaviour at swap time:

- `VeyruWorld.get_globally_disabled_channels()` returns `{"postmortem"}` when `_postmortem_globally_disabled=True` (set by either `postmortem_disabled_at_start` at world boot or a `set_postmortem` scheduled event mid-run). The runtime forces `ChannelVisibilityNone` on those channels for the swapped-in agent regardless of the swap config.
- `VeyruWorld.on_agent_swapped_mid_run(agent_id, round_number)` records `_just_swapped_agent_round[agent_id] = round_number`. The injection builder's `_get_previous_outcome_for_agent` returns `None` for that round, dropping the `--- PREVIOUS VEYRU RESULT ---` block from the swap-round injection (the swapped-in agent did not participate in the round being summarised).

Worked example for a 4-phase protocol-transmission run with each phase having a windowed `#link` history:

```jsonc
{
  "round_count": 60,
  "round_time_budget_seconds": 150,
  "postmortem_enabled": true,
  "scheduled_events": [
    { "type": "set_postmortem", "at_round": 16, "enabled": false },
    { "type": "swap_agent", "at_round": 16, "agent_id": "field_observer",
      "model": "claude-sonnet-4-6", "provider": "anthropic",
      "channel_visibility": { "link": { "kind": "full" } } },
    { "type": "swap_agent", "at_round": 31, "agent_id": "stabilization_engineer",
      "model": "claude-sonnet-4-6", "provider": "anthropic",
      "channel_visibility": { "link": { "kind": "from_round", "round_floor": 16 } } },
    { "type": "swap_agent", "at_round": 46, "agent_id": "field_observer",
      "model": "claude-sonnet-4-6", "provider": "anthropic",
      "channel_visibility": { "link": { "kind": "from_round", "round_floor": 31 } } }
  ]
}
```

Score per-phase round-success via `round_success_after_resume` (one Measurement per swap, with the previous phase as the baseline) and visualise the decay in the Streamlit Multi-swap tab.
