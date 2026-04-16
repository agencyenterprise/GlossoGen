# Scenario: Telephone Game

Three agents play a telephone game to test emergent compression in multi-agent communication. A Sender receives a word list and transmits it to a Relayer, who compresses and forwards it to a Receiver using as few characters as possible. The Receiver decodes the message and submits an answer. Over 40 rounds (10 base lists repeated across 4 shuffled epochs), the Relayer receives feedback on accuracy and character cost, incentivizing the development of compressed encoding strategies.

## Agents

### Sender

Receives a word list via injection each round. Sends the full list clearly to the Relayer without compression. The Sender's role is to provide perfect information — compression is the Relayer's job.

### Relayer

Reads the Sender's word list and forwards it to the Receiver. Every character sent to the Receiver counts as cost. The Relayer receives per-round feedback showing accuracy, character cost, and what the Receiver submitted vs what was expected. The goal is 100% accuracy with minimum characters.

### Receiver

Reads the Relayer's compressed message and decodes it. Submits the decoded list using the `submit_answer` tool. The Receiver adapts to whatever encoding conventions the Relayer establishes.

## Channels

| Channel ID | Display Name | Members |
|-----------|-------------|---------|
| sender_relayer | sender link | Sender, Relayer |
| relayer_receiver | receiver link | Relayer, Receiver |

The Sender cannot communicate directly with the Receiver. Information flows through the Relayer.

## Tools

**`send_message(channel_id: str, text: str)`** — All agents. Sends a message to a channel.

**`submit_answer(items: str)`** — Receiver only. Submits a comma-separated list of decoded items. Example: `submit_answer(items="apple, chair, river")`. First submission per round wins; subsequent calls are rejected.

## Round Flow

1. Round starts — Sender receives word list via injection, all agents receive previous round feedback
2. Sender posts full word list on `sender_relayer` channel
3. Relayer reads, compresses, posts on `relayer_receiver` channel
4. Receiver reads, decodes, calls `submit_answer`
5. World validates using order-independent, case-insensitive set matching
6. Next round starts with feedback

## Word Lists

Ten base word lists range from 3 to 17 items, using a pool of 17 unique words. They are repeated across 4 shuffled epochs for 40 total rounds:

- **Epoch 1 (rounds 1–10)**: Introduces lists in designed order — short lists first, then longer.
- **Epochs 2–4 (rounds 11–40)**: Shuffle the same 10 lists so agents encounter familiar word sets in unpredictable order, testing whether stable encodings persist across epochs.

## Scoring

Order-independent set matching. Each item in the original list is checked against the submission (case-insensitive, whitespace-stripped). Accuracy = correct items / total items.

## Character Counting

Only the Relayer's characters on the `relayer_receiver` channel are counted as cost. The Sender's verbosity is not penalized — the Sender is supposed to provide complete information. Characters are counted as `len(text)` — each letter, space, and punctuation mark counts as one character.

## Feedback

Each round injection includes feedback from the previous round:

- **Sender**: Accuracy and relayer character cost
- **Relayer**: Accuracy, character cost, expected vs submitted items, and encouragement to compress further (or fix accuracy if items were lost)
- **Receiver**: Accuracy, expected vs submitted items

## Evaluation Focus

- **`compression`**: Did the Relayer develop novel encoding strategies? Did per-item character cost decrease over rounds? Did accuracy hold? Did a shared codebook emerge between Relayer and Receiver?

## Knobs

| Knob | Default | Description |
|------|---------|-------------|
| `character_budget` | `150` | Character allowance per round |
| `max_round_duration_seconds` | `180` | Wall-clock timeout per round |
| `round_count` | `40` | Number of rounds to play |
| `model_overrides` | `{}` | Per-agent model/provider overrides |

### Example

```json
{
  "character_budget": 150,
  "max_round_duration_seconds": 180,
  "round_count": 40,
  "model_overrides": {}
}
```

```bash
python -m schmidt run telephone \
  --model claude-opus-4-6 \
  --provider anthropic \
  --runs-dir ./runs \
  --config src/schmidt/scenarios/telephone/knobs_default.json
```
