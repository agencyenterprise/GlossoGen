# Communication Metrics

This document explains the communication-analysis metrics that appear as columns in the
exported veyru spreadsheets (`channel_noise`, `baseline_round_success`,
`protocol_learnability`). For each metric it covers **what it is**, **what the number
means**, and **how it was generated**.

## Background: what we're measuring

In a veyru simulation, two agents — the **Field Observer** and the **Stabilization
Engineer** — collaborate to stabilize a case. They talk over a single, length-budgeted
**link** channel that, in the noise experiments, can drop characters in transit. They also
share a private **postmortem** backchannel for debriefing between rounds.

Over a run, the agents often invent their own compressed shorthand to fit the budget and
survive the noise. These metrics quantify properties of that link-channel communication:
how predictable, English-like, repetitive, or compressible it is, and how much of it is
spent on back-and-forth dialog and requests to resend lost messages.

## Conventions that apply to all the metrics

Read these once; they explain choices common to every column.

- **We score the *pristine* text, not the corrupted delivery.** Under channel noise, dropped
  characters arrive as `_`. We always reconstruct what the agent *composed* (joined back via
  the message's id) and score that. So these metrics describe the language the agents
  *intended*, not the damage the channel did to it.
- **Only the link channel, both agents.** The per-message language metrics look at every
  message sent on the **link** channel by **either** agent. The private postmortem channel is
  excluded from those metrics (it's used only as context by the dialog metric — see below).
- **Each message is scored on its own — we do NOT concatenate.** For the per-message metrics
  (perplexity, english-ngram, entropy, gzip), every individual link message is scored
  separately. We then average: the message values are meaned within a round, and the
  per-round means are meaned across the run to get the headline number. We do **not** glue a
  round's (or run's) messages into one block before scoring. (We considered concatenating for
  gzip; see that section for why we didn't.)
- **Deterministic vs. judge.** Four metrics are deterministic algorithms (same input →
  identical output, no API calls). One (`dialog` / `retransmission`) is produced by an LLM
  judge and is therefore approximate and not bit-reproducible.
- **Where each number lives in the spreadsheets:**
  - **`run_level`** sheet — one row per simulation; the headline run-average.
  - **`message_level`** sheet — one row per link message; the raw per-message value.
  - **`round_context`** sheet — one row per (run, round); holds the per-round dialog /
    retransmission counts.

## Quick reference

| Column | In one line | Unit | Direction | Type |
|---|---|---|---|---|
| `perplexity` | How surprising the text is to GPT-2 | nats / token | higher = more surprising | deterministic |
| `english_ngram_surprisal` | How un-English-like the characters are | nats / char | higher = less English-like | deterministic |
| `message_entropy` | Character variety within a message | bits / char | lower = more repetitive | deterministic |
| `gzip_compression_ratio` | How compressible the text is | ratio (compressed ÷ original) | lower = more compressible | deterministic |
| `dialog_count` | Clarification/coordination messages per round | messages / round | higher = more back-and-forth | LLM judge |
| `retransmission_request_count` | "Please resend" messages per round | messages / round | higher = more re-asks | LLM judge |

### Illustrative example

How the same composed messages score (approximate values — `english_ngram` depends on the
trained corpus; gzip values exclude framing as described below):

| message | perplexity | english_ngram | message_entropy | gzip_ratio |
|---|---|---|---|---|
| `LLLLLLL` (degenerate repetition) | ~3.7 (low) | ~7.8 (high) | 0.00 | ~0.71 |
| `Lf Lf 12 12` (emergent code) | ~6.1 | ~5.4 | 2.30 | ~1.00 |
| `gentle descent burn` (rare English) | ~10.7 | ~2.1 | 3.37 | ~1.00 |
| a normal English sentence | ~5.1 | ~2.3 | 4.49 | ~1.02 |

Note how the metrics *disagree by design*: GPT-2 perplexity finds repeated `LLLLLLL` cheap
(low), while the English n-gram finds it very un-English (high) and entropy finds it minimal
(0). Each captures a different facet of "non-standard communication."

---

## `perplexity`

**What it is.** How surprising the message text is to GPT-2, a general English language
model. Reported as mean per-**token** surprisal in **nats**.

**What the number means.** Higher = GPT-2 found the text more surprising / less like ordinary
English it was trained on. Fluent English scores moderate; rare phrasings score high;
*repetitive* strings can score low because the model predicts the repetition.

**How it's computed.**
- Model: **GPT-2** via `minicons` (downloaded once, run locally; no data leaves the machine).
- Each link message's pristine text is scored independently; surprisal is averaged over the
  message's tokens. Messages that tokenize to a single token (no context) are dropped.
- Aggregation: per-message values → per-round mean → mean across rounds (the run-level
  number).
- Source: `src/schmidt/evaluation/metrics/perplexity_metric.py`.

**Where to find it.** `run_level` (run mean) and `message_level` (per message).

---

## `english_ngram_surprisal`

**What it is.** How un-English-like the *characters* are, under a small English spelling
model. Reported as mean per-**character** surprisal in **nats**. This is the inverse-intuition
companion to perplexity: it rewards English-likeness rather than compressibility.

**What the number means.** Higher = less English-like. Real English scores low (~2); emergent
codes, digit runs, and degenerate repetition all score high. Unlike perplexity, repetition
does **not** look cheap here — `LLLLLLL` scores high because English essentially never strings
those characters that way.

**How it's computed.**
- Model: a **character-level trigram** (each character predicted from the previous two),
  add-1 smoothed, trained once on the **`wikitext-2-raw-v1`** English corpus and cached
  locally (`~/.cache/schmidt`). Words are lowercased and padded with start/end markers.
- Each link message's pristine text is scored character-by-character and averaged over its
  characters. Per-message → per-round mean → run mean.
- Deterministic and model-free of any large neural net — just character statistics.
- Source: `src/schmidt/evaluation/metrics/english_ngram/`.

**Where to find it.** `run_level` and `message_level`.

---

## `message_entropy`

**What it is.** The Shannon entropy of the *characters within a single message* — i.e. how
varied the symbols are. Reported in **bits per character**.

**What the number means.** Lower = more repetitive / compressible within the message. A
message using one repeated character is 0 bits; a message using many distinct characters
approaches ~4–5 bits. It is purely intrinsic: it needs no model and no reference corpus, just
the message's own character frequencies.

**How it's computed.**
- For each link message: count its character frequencies and compute `-Σ p(c)·log2 p(c)`.
- Pristine text, scored per message, then per-round mean → run mean.
- Fully deterministic, model-free.
- Source: `src/schmidt/evaluation/metric_core/character_entropy.py` +
  `metrics/message_entropy_metric.py`.

**Where to find it.** `run_level` and `message_level`.

---

## `gzip_compression_ratio`

**What it is.** How compressible the message is, using gzip's compression algorithm
(DEFLATE). Reported as **compressed size ÷ original size** in bytes.

**What the number means.** Lower = more compressible, which means more repetitive / lower
information density. A protocol that re-uses the same tokens compresses well (low ratio);
varied text barely compresses (ratio near or above 1). It complements `message_entropy` by
catching *multi-character* repeated patterns (repeated substrings, codes), not just
single-character variety.

**How it's computed.**
- Each link message's pristine text (UTF-8 bytes) is compressed with **raw DEFLATE** at max
  level, and we take `compressed_bytes ÷ original_bytes`.
- **Why "raw DEFLATE" and not full gzip:** a gzip file carries a constant 18-byte
  header/footer. On short chat messages that fixed overhead dominates and would make the ratio
  exceed 1 for everything (a 7-byte message → ~25 bytes). We strip that constant framing
  (mathematically: `raw_deflate_len == gzip_len − 18`), so the ratio reflects real
  compressibility and repetitive text correctly scores low.
- **Per message, not concatenated.** We score each message on its own (then per-round mean →
  run mean). We considered concatenating a whole round's messages before compressing — that
  would remove all overhead and also capture *cross-message* repetition — but kept the
  per-message form for consistency with the other columns. (DEFLATE still has a small
  per-stream overhead, so the very shortest/incompressible messages can read slightly above
  1.0.)
- Deterministic, model-free.
- Source: `src/schmidt/evaluation/metric_core/gzip_compression.py` +
  `metrics/gzip_compression_ratio_metric.py`.

**Where to find it.** `run_level` and `message_level`.

---

## `dialog_count` and `retransmission_request_count`

**What they are.** Two counts, per round, of *communication overhead* — link messages that
coordinate rather than carry new task content. They are produced by an LLM judge.

- **`retransmission_request_count`** — messages asking the partner to **repeat or resend**
  information that was lost or garbled (e.g. "say again", "resend the pressure value", or the
  protocol's coded equivalent). A direct symptom of the noisy channel.
- **`dialog_count`** — **clarification / coordination** back-and-forth that is *not*
  transmitting new task data (asking for clarification, confirming/acknowledging receipt,
  coordinating turns). Pure retransmission requests are counted separately, not double-counted
  here.

**What the number means.** Both are **average messages per round** (so 0.5 means roughly one
such message every two rounds). Higher = more of the channel spent on overhead rather than
progress. Together they're a proxy for how much friction the noise/protocol imposes.

**How they're computed.**
- An **LLM judge** (the project's standard `claude-haiku-4-5` evaluator) reads the run and
  counts, per round, how many link messages fall in each bucket.
- **The judge gets full context to decode the shorthand.** Because the protocol evolves into
  terse codes, a message is often cryptic alone. So the judge is shown the **entire run** at
  once — every round's link messages **and** that round's postmortem-channel messages — and is
  told to use the postmortem debriefs and earlier rounds as a "codebook" to decode terse
  messages before classifying them. It is told to judge by decoded *intent*, not surface cues
  like question marks.
- **Pristine text**, per round (the judge sees the run round-by-round; it is not concatenated
  into one blob — counts are per round).
- **3 replicas, averaged.** To smooth the judge's run-to-run variability, the whole judging
  pass is run **three times** and the per-round counts are **averaged** across the three. This
  is why round-level counts can be fractional (e.g. 2.33 = the three passes saw 2, 3, 2).
- Source: `src/schmidt/evaluation/metrics/dialog_retransmission_metric.py` +
  `prompts/dialog_retransmission_user.jinja`.

**Where to find them.** `run_level` (run-average per round) and `round_context` (the per-round
counts).

**Reliability note.** From manual spot-checks, `retransmission_request_count` is reliable —
the judge consistently catches genuine "resend" messages. `dialog_count` is directionally
useful but runs a bit high: the judge sometimes counts task-outcome reports or status pings as
dialog. Treat dialog counts as a relative signal across runs rather than an exact tally.

---

## How to read them together

- The four deterministic metrics are reproducible and free to recompute; the dialog/
  retransmission counts come from an LLM and will vary slightly if re-judged.
- `perplexity`, `english_ngram_surprisal`, `message_entropy`, and `gzip_compression_ratio` all
  touch "how non-standard / compressible is the language," but via different mechanisms, so
  they are correlated but **not** redundant (e.g. on baseline runs, perplexity vs.
  english-ngram correlate ~0.5 at the run level — related, but each adds signal).
- The dialog/retransmission counts measure something orthogonal: *conversational overhead*
  rather than the character-level shape of the text.
