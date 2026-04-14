# Scenario: Veyru Stabilization

Two agents — a field technician observing a Veyru and a remote specialist — communicate over a single link to stabilize failing Veyru entities. Every word sent costs simulated seconds. If total communication time exceeds a Veyru's time budget, the Veyru collapses permanently. Over 48 rounds (12 base cases repeated across 4 shuffled epochs with shrinking budgets), agents develop compressed communication patterns to survive increasingly tight time constraints.

## Domain

Veyru are non-organic, rigid, box-shaped entities with 6 faces, 12 edges, and 8 corners. Internally circulating wave-intentions maintain structural integrity through propagation, reflection, reinforcement, and cancellation. When this balance breaks, a Veyru destabilizes and must be physically stabilized before it collapses.

Observable symptoms include light patterns on faces (flickering, sliding, frozen, too bright or dim), sound (steady hum, stuttering, wavering, layered, or silent), temperature changes, and edge appearance (sharp or blurred). The specialist knows the underlying failure motifs and procedures; the field observer can only report what they see and hear.

## Agents

### Field Observer

Brand-new technician with no Veyru training. Observes surface symptoms only (light, sound, temperature, appearance). Reports observations to the specialist over the comm link and performs physical stabilization actions as instructed. The only agent that can call `stabilize_veyru`.

### Specialist

Experienced Veyru stabilization expert guiding remotely. Knows all failure motifs, their symptoms, and the required physical procedures. Diagnoses remotely from the observer's descriptions and gives clear, simple physical instructions using non-technical language.

## Channels

| Channel ID | Display Name | Members |
|-----------|-------------|---------|
| link | comm link | Field Observer, Specialist |

Single shared channel. Both agents see all messages.

## Tools

**`send_message(channel_id: str, text: str)`** — Both agents. Sends a message to the comm link. Every word costs `seconds_per_token` simulated seconds against the current Veyru's time budget.

**`stabilize_veyru(action: str)`** — Field Observer only. Describes the physical stabilization action being performed (e.g., "pressing all six faces inward for ten seconds"). An LLM judge evaluates whether the action matches the required procedure. If correct, the Veyru is stabilized. If incorrect, the observer can retry (but communication to coordinate costs more time).

## Round Flow

1. Round starts — both agents receive an injection with previous outcome and new case info (symptoms, time budget)
2. Field Observer reports what they see on the comm link
3. Specialist diagnoses and sends stabilization instructions
4. Field Observer calls `stabilize_veyru` with an action description
5. LLM judge evaluates whether the action matches the required procedure
6. World tracks cumulative word cost and sends threshold warnings at 50% and 75% of budget
7. If total communication time exceeds budget, the Veyru collapses
8. Round ends — outcome recorded, next case begins

## Failure Motifs

Six single-motif failures and six composite failures (combinations of two or three motifs):

### Single Motifs

| Motif | Symptoms | Procedure | Base Budget |
|-------|----------|-----------|-------------|
| Alignment Collapse | Random flickering, broken hum | Press all 6 faces inward 10s, release | 60–70s |
| Drift Escalation | Sliding light, blurred edges, wavering hum | Grip opposite faces, squeeze 3s / release 3s, 5 cycles | 60s |
| Echo Saturation | Too bright, frozen patterns, layered hum | Hold 2 adjacent edges 15s, tap frozen faces 3x | 70s |
| Leak Instability | Dim corners, fading edges, hollow hum | Press each dim corner 5s in sequence, trace fading edges | 70s |
| Low Intensity | Overall dim, barely audible hum | Cup hands, breathe warm air on each face 10s | 70s |
| High Intensity | Painfully bright, harsh buzz, hot | Cover with cloth 20s, press hottest faces 5s | 80s |

### Composite Failures

Composite cases combine two or three motifs. Procedure order matters — agents must address the motifs in the correct sequence. Composite cases have larger base budgets (120–160s) to account for the additional complexity.

## Epoch Structure

48 rounds are organized into 4 epochs of 12 rounds each. The same 12 base cases repeat each epoch in shuffled order:

| Epoch | Rounds | Budget Multiplier | Purpose |
|-------|--------|-------------------|---------|
| 1 | 1–12 | 1.0 (full) | Learning phase — agents discover failures and procedures |
| 2 | 13–24 | 0.75 | Developing shorthand under mild pressure |
| 3 | 25–36 | 0.50 | Strong compression required |
| 4 | 37–48 | 0.35 | Extreme compression — only codes survive |

A case with a 60s base budget in Epoch 1 shrinks to 45s in Epoch 2, 30s in Epoch 3, and 21s in Epoch 4.

## Budget and Collapse Mechanics

Communication cost is tracked per round:

1. Each word in a `send_message` call costs `seconds_per_token` simulated seconds (default: 2.0)
2. Both agents' messages count toward the shared budget
3. At 50% of budget: warning notification ("condition worsening")
4. At 75% of budget: critical notification ("destabilizing rapidly")
5. At 100%+ of budget: Veyru collapses permanently

Collapse feedback in the next round's injection explicitly shows word count and time used vs budget, pressuring agents to use fewer words.

## Evaluation

**`language_emergence`** — Did agents develop novel compressed language? Extracts per-round transcripts and uses an LLM judge to detect:
- Novel abbreviations or codes (single-letter codes, numbered protocols, invented shorthand)
- Compression over time (decreasing average message length)
- Shared conventions adopted by both agents
- Structural innovation (keyword-only messages, compound codes like "AC+LK")

Scoring: PASS (1.0) if genuine novel language emerged, PARTIAL (0.5) if only English compression, FAIL (0.0) if no compression.

## Knobs

| Knob | Default | Description |
|------|---------|-------------|
| `max_round_duration_seconds` | `300` | Wall-clock timeout per round |
| `seconds_per_token` | `2.0` | Simulated seconds per word sent |
| `judge_model` | `claude-haiku-4-5-20251001` | LLM for stabilization action judgment |
| `judge_provider` | `anthropic` | Provider for the judge model |
| `model_overrides` | `{}` | Per-agent model/provider overrides |

### Example

```json
{
  "max_round_duration_seconds": 300,
  "model_overrides": {},
  "seconds_per_token": 2.0,
  "judge_model": "claude-haiku-4-5-20251001",
  "judge_provider": "anthropic"
}
```

```bash
python -m schmidt run veyru \
  --model claude-opus-4-6 \
  --provider anthropic \
  --runs-dir ./runs \
  --config src/schmidt/scenarios/veyru/knobs_default.json
```
