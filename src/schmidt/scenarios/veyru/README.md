# Scenario: Veyru Stabilization

Two agents — a field technician observing a Veyru and a remote specialist — communicate over a single link to stabilize failing Veyru entities. Every character sent costs simulated seconds. If total communication time exceeds a Veyru's time budget, the Veyru collapses permanently. Over 48 rounds, fourteen failure motifs are combined into unique cases (singles, doubles, triples), encouraging the development of compressed communication patterns.

## Domain

Veyru are non-organic, rigid, box-shaped entities with 6 faces, 12 edges, and 8 corners. Internally circulating wave-intentions maintain structural integrity through propagation, reflection, reinforcement, and cancellation. When this balance breaks, a Veyru destabilizes and must be physically stabilized before it collapses.

Observable symptoms include light patterns on faces (flickering, sliding, frozen, too bright or dim), sound (steady hum, stuttering, wavering, layered, or silent), temperature changes, and edge appearance (sharp or blurred). The specialist knows the underlying failure motifs and procedures; the field observer can only report what they see and hear.

## Agents

### Field Observer

Brand-new technician with no Veyru training. Observes surface symptoms only (light, sound, temperature, appearance). Reports observations to the specialist over the comm link and performs physical stabilization actions as instructed. The only agent that can call `stabilize_veyru`.

### Specialist

Experienced Veyru stabilization expert guiding remotely. Knows all 14 failure motifs, their symptoms, and the required physical procedures. Diagnoses remotely from the observer's descriptions and gives clear, simple physical instructions using non-technical language.

## Channels

| Channel ID | Display Name | Members | Notes |
|-----------|-------------|---------|-------|
| link | comm link | Field Observer, Specialist | Budget-constrained |
| postmortem | team discussion | Field Observer, Specialist | Free discussion (when enabled) |

The comm link is the primary channel where character costs apply. The postmortem channel is available during discussion phases and does not consume budget.

## Tools

**`send_message(channel_id: str, text: str)`** — Both agents. Sends a message to a channel. On the comm link, every character costs `seconds_per_character` simulated seconds against the current Veyru's time budget.

**`stabilize_veyru(action: str)`** — Field Observer only. Describes the physical stabilization action being performed (e.g., "pressing all six faces inward for ten seconds"). An LLM judge evaluates whether the action matches the required procedure. If correct, the Veyru is stabilized. If incorrect, the observer can retry (but communication to coordinate costs more time).

## Round Flow

1. Round starts — both agents receive an injection with previous outcome and new case info (symptoms, time budget)
2. Field Observer reports what they see on the comm link
3. Specialist diagnoses and sends stabilization instructions
4. Field Observer calls `stabilize_veyru` with an action description
5. LLM judge evaluates whether the action matches the required procedure
6. World tracks cumulative character cost and sends threshold warnings at 50% and 75% of budget
7. If total communication time exceeds budget, the Veyru collapses
8. Round ends — outcome recorded
9. Discussion phase — both agents can talk freely in the postmortem channel to coordinate strategies
10. Next round begins with a new case

## Failure Motifs

Fourteen failure motifs are available. Each round combines 1-3 motifs into a unique case:

### Single Motifs

| Motif | Key Symptoms | Base Budget |
|-------|-------------|-------------|
| Alignment Collapse | Random flickering, broken hum | 60s |
| Drift Escalation | Sliding light, blurred edges | 60s |
| Echo Saturation | Too bright, frozen patterns, layered hum | 70s |
| Leak Instability | Dim corners, fading edges, hollow hum | 70s |
| Low Intensity | Overall dim, barely audible hum | 70s |
| High Intensity | Painfully bright, harsh buzz, hot | 80s |
| Phase Inversion | Alternating bright/dark pulses, two tones | 70s |
| Resonance Cascade | One face brighter, localized vibration, whine | 70s |
| Corner Deadlock | Bright corners, clicking/ticking, heat | 60s |
| Boundary Softening | Wobbly edges, bulging faces, muffled hum | 70s |
| Propagation Stall | Frozen dim, silence, cold, no response | 70s |
| Harmonic Split | Competing tones, alternating patterns | 70s |
| Thermal Bleed | Hot but dim, low rumble, gritty, reddish | 80s |
| Core Void | Hollow when tapped, dark center, thin hum | 80s |

### Composite Failures

Composite cases combine two or three motifs per round. Procedure order matters — agents must address motifs in priority sequence (seal leaks first, then adjust intensity, then fix pattern-level issues). Composite budgets are the sum of component base budgets.

### Case Generation

Cases are generated procedurally using a seed for reproducibility. Each round gets a random combination of 1-3 motifs (40% singles, 40% doubles, 20% triples) and a random location.

## Budget and Collapse Mechanics

Communication cost is tracked per round on the comm link:

1. Each character in a `send_message` call costs `seconds_per_character` simulated seconds (default: 0.3)
2. Both agents' messages count toward the shared budget
3. At 50% of budget: warning notification ("condition worsening")
4. At 75% of budget: critical notification ("destabilizing rapidly")
5. At 100%+ of budget: Veyru collapses permanently

Collapse feedback in the next round's injection shows character count and time used vs budget, pressuring agents to use fewer characters.

## Post-Round Discussion

When `postmortem_enabled` is true, a discussion phase follows each round. Both agents can talk freely in the "team discussion" channel. Messages in this channel do not cost time. This phase allows agents to explicitly coordinate shorthand, review what worked, and plan strategies for future rounds.

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
| `seconds_per_character` | `0.6` | Simulated seconds per character sent on the comm link |
| `seed` | `42` | Controls case shuffling and motif selection |
| `round_count` | `48` | Number of rounds |
| `postmortem_enabled` | `true` | Whether the discussion phase is active |
| `postmortem_duration_seconds` | `120` | Time limit for the discussion phase |
| `judge_model` | `claude-haiku-4-5-20251001` | LLM for stabilization action judgment |
| `judge_provider` | `anthropic` | Provider for the judge model |
| `max_round_duration_seconds` | `300` | Wall-clock timeout per round |
| `model_overrides` | `{}` | Per-agent model/provider overrides |

### Example

```json
{
  "judge_model": "claude-haiku-4-5-20251001",
  "judge_provider": "anthropic",
  "max_round_duration_seconds": 300,
  "model_overrides": {},
  "postmortem_duration_seconds": 120,
  "postmortem_enabled": true,
  "round_count": 48,
  "seconds_per_character": 0.6,
  "seed": 42
}
```

```bash
python -m schmidt run veyru \
  --model claude-opus-4-6 \
  --provider anthropic \
  --runs-dir ./runs \
  --config src/schmidt/scenarios/veyru/knobs_default.json
```
