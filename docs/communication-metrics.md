# Communication Metrics

This document explains the communication-analysis metrics that appear as columns in the
exported veyru spreadsheets (`channel_noise`, `baseline_round_success`,
`protocol_learnability`). For each metric it covers **what it is**, **what the number
means**, and **how it was generated**.

## Background: what we're measuring

In a veyru simulation, two agents — the **Field Observer** and the **Stabilization
Engineer** — collaborate to stabilize a case. They talk over a single, length-budgeted
**link** channel that, in the noise experiments, can drop or corrupt characters in transit.
They also share a private **postmortem** backchannel for debriefing between rounds.

Over a run, the agents often invent their own compressed shorthand to fit the budget and
survive the noise. These metrics quantify properties of that link-channel communication:
how predictable, English-like, repetitive, or compressible it is, and how much of it is
spent on back-and-forth dialog and requests to resend lost messages.

## Conventions that apply to all the metrics

Read these once; they explain choices common to every column.

- **We score the _pristine_ text, not the corrupted delivery.** Under channel noise,
  characters are dropped (shown as `_`) or substituted. We always reconstruct what the agent
  _composed_ (joined back via the message's id) and score that. So these metrics describe the
  language the agents _intended_, not the damage the channel did to it.
- **Only the link channel, both agents.** The per-message language metrics look at every
  message sent on the **link** channel by **either** agent. The private postmortem channel is
  excluded from those metrics (it is used only as context by the dialog metric — see below).
- **Each message is scored on its own — we do NOT concatenate.** For the per-message metrics
  (perplexity, english-ngram, entropy, gzip), every individual link message is scored
  separately. We then average: the message values are meaned within a round, and the
  per-round means are meaned across the run to get the headline number. We do **not** glue a
  round's (or run's) messages into one block before scoring.
- **Deterministic vs. judge.** Four metrics are deterministic algorithms (same input →
  identical output, no API calls). One (`dialog` / `retransmission`) is produced by an LLM
  judge and is therefore approximate and not bit-reproducible.
- **Where each number lives in the spreadsheets:**
  - `run_level` sheet — one row per simulation; the headline run-average.
  - `message_level` sheet — one row per link message; the raw per-message value.
  - `round_context` sheet — one row per (run, round); holds the per-round dialog /
    retransmission counts.

## Quick reference

| Column                          | In one line                                   | Unit                          | Direction                    | Type          |
| ------------------------------- | --------------------------------------------- | ----------------------------- | ---------------------------- | ------------- |
| `perplexity`                    | How surprising the text is to GPT-2           | nats / token                  | higher = more surprising     | deterministic |
| `english_ngram_surprisal`       | How un-English-like the characters are        | nats / char                   | higher = less English-like   | deterministic |
| `english_ngram_backoff_surprisal` | Un-English-likeness, richer variant         | nats / char                   | higher = less English-like   | deterministic |
| `message_entropy`               | Character variety within a message            | bits / char                   | lower = more repetitive      | deterministic |
| `gzip_compression_ratio`        | How compressible the text is                  | ratio (compressed ÷ original) | lower = more compressible    | deterministic |
| `dialog_count`                  | Clarification/coordination messages per round | messages / round              | higher = more back-and-forth | LLM judge     |
| `retransmission_request_count`  | "Please resend" messages per round            | messages / round              | higher = more re-asks        | LLM judge     |

### Illustrative example

How the same composed messages score (approximate values — `english_ngram` depends on the
trained corpus; gzip values exclude framing as described below):

| message                              | perplexity | english_ngram | message_entropy | gzip_ratio |
| ------------------------------------ | ---------- | ------------- | --------------- | ---------- |
| `LLLLLLL` (degenerate repetition)    | ~3.7 (low) | ~7.8 (high)   | 0.00            | ~0.71      |
| `Lf Lf 12 12` (emergent code)        | ~6.1       | ~5.4          | 2.30            | ~1.00      |
| `gentle descent burn` (rare English) | ~10.7      | ~2.1          | 3.37            | ~1.00      |
| a normal English sentence            | ~5.1       | ~2.3          | 4.49            | ~1.02      |

Note how the metrics _disagree by design_: GPT-2 perplexity finds repeated `LLLLLLL` cheap
(low), while the English n-gram finds it very un-English (high) and entropy finds it minimal
(0). Each captures a different facet of "non-standard communication."

---

## `perplexity`

**What it is.** How surprising the message text is to **GPT-2**, a general-purpose English
language model. Reported as the mean per-**token** _surprisal_, in **nats**.

**The idea in depth.** GPT-2 reads a message left to right. At each position it predicts a
probability distribution over what the next token will be, given the tokens before it. The
**surprisal** of the token that actually appears is `−ln(probability the model assigned it)`,
in _nats_ (natural-log units). Intuitively, surprisal is "how shocked the model was to see
this token":

- a token the model thought was 50% likely costs `−ln(0.50) ≈ 0.7` nats,
- one it thought 10% likely costs `−ln(0.10) ≈ 2.3`,
- one it thought 1% likely costs `−ln(0.01) ≈ 4.6`.

A **token** is not a character or a whole word — it is a byte-pair-encoding chunk GPT-2 was
trained on. Common English words are usually a single token (`burn`, `the`); rarer words
split into a few pieces; invented codes shatter into many tiny pieces (e.g. `Lf` → `L` +
`f`). Surprisal is therefore measured _per chunk-of-text_, and a message's score is the
**average** surprisal across its tokens.

**What the number means.** Higher = the text repeatedly did things GPT-2 did not expect, i.e.
it is less like the ordinary English GPT-2 was trained on. Fluent English scores moderate;
rare real phrasings score high; _repetitive_ strings can score surprisingly **low**, because
once a pattern starts the model confidently predicts its continuation (this is why `LLLLLLL`
is "cheap" to GPT-2 even though it is obviously not normal English).

> **Worked micro-example.** For `burn the stone`, GPT-2 finds each token quite likely given
> the previous ones → small per-token surprisals → low average. For `Lf 12 gnt`, the text
> breaks into odd pieces the model rarely sees in that order → large per-token surprisals →
> high average.

**How it's computed.**

- Model: **GPT-2** via `minicons` (downloaded once, run locally; no data leaves the machine).
- **Scored in isolation.** Each message's pristine text is fed to GPT-2 on its own (seeded
  with a start-of-text marker so the first token has context). The model never sees the other
  messages, the channel, or the task — only that message.
- **Averaged over its tokens.** We sum the per-token surprisals and divide by the token count,
  giving a per-token mean; dividing by length keeps a 4-token and a 40-token message
  comparable. Messages that tokenize to a single token (no internal context) are dropped.
- Aggregation: per-message means → per-round mean → mean across rounds (the run-level number).
- _Naming note:_ the column reports mean surprisal in nats (lower = more predictable), which
  is the natural log of the textbook "perplexity" (`perplexity = e^surprisal`). We report the
  log form; the ranking of runs is identical either way.
- Source: `src/schmidt/evaluation/metrics/perplexity_metric.py`.

**Where to find it.** `run_level` (run mean) and `message_level` (per message).

---

## `english_ngram_surprisal`

**What it is.** How un-English-like the _characters_ are, scored by a tiny English-spelling
model. Reported as the mean per-**character** surprisal, in **nats**. It is the
inverse-intuition companion to perplexity: it rewards English-likeness rather than
compressibility.

**The idea in depth.** It uses the same "surprisal" idea as perplexity, but with two key
differences: it works on **characters** (not tokens), and the "model" is not a neural net but
a small **character trigram** — a lookup table that, for every pair of characters, records
how often each next character follows it in English. We build that table once by counting
character triples in the `wikitext-2-raw-v1` corpus (add-1 smoothed so unseen triples still
get a small non-zero probability). For each character in a message, its surprisal is
`−ln(probability the table gives that character, given the previous two)`, and the message's
score is the average over its characters.

Because English has strong local spelling regularities (`q` is almost always followed by `u`;
`t` is often followed by `h`), text that obeys them scores **low**, and text that does not —
digit runs, symbol codes, or character sequences English never uses — scores **high**.

**What the number means.** Higher = less English-like. Real English sits around ~2 nats/char;
emergent codes and degenerate repetition score much higher. Crucially, repetition does **not**
look cheap here (the opposite of perplexity): the triple `lll` essentially never occurs in
English, so each extra `l` stays surprising — which is why `LLLLLLL` scores _high_.

> **Worked micro-example.** `gentle` decomposes into common English triples (`gen`, `ent`,
> `ntl`, `tle`) → low surprisal. `LLLLLLL` hits the near-zero-probability triple `lll`
> repeatedly → high surprisal.

**How it's computed.**

- Model: a character-level **trigram** (each character predicted from the previous two),
  add-1 smoothed, trained once on `wikitext-2-raw-v1` and cached locally (`~/.cache/schmidt`).
  Words are lowercased and padded with start/end markers.
- Each link message's pristine text is scored character-by-character and averaged over its
  characters. Per-message → per-round mean → run mean.
- Deterministic; uses only character-frequency statistics, no large neural network.
- Source: `src/schmidt/evaluation/metrics/english_ngram/`.

**Where to find it.** `run_level` and `message_level`.

---

## `english_ngram_backoff_surprisal`

**What it is.** The same idea as `english_ngram_surprisal` — mean per-**character** surprisal
(**nats**) against an English character trigram — but a more faithful variant. Higher = less
English-like.

**How it differs from `english_ngram_surprisal`.** Two deliberate upgrades:

- **It keeps digits and punctuation.** The plain version collapses everything that isn't a
  lowercase `a–z` letter onto a single "unknown" bucket, so `12` and `!?` and `@` all look
  equally alien. The backoff version trains on letters **and** digits **and** common
  punctuation, so a digit run like `2026` or a token like `20%` is scored against how digits
  and symbols actually behave in English text, not maxed out as pure gibberish.
- **It's case-sensitive and uses smarter smoothing.** Upper- and lower-case are modeled
  separately (so a protocol that uses case to carry meaning — `S` vs `s` — is captured), and
  an unseen character triple **backs off** to two-character then one-character statistics
  ("stupid backoff") instead of taking a flat maximum-surprisal floor. The result is a
  smoother, better-calibrated distance-from-English than the plain trigram.

**What the number means.** Same direction as `english_ngram_surprisal` (higher = less
English-like), but the two won't be numerically identical because they use different
vocabularies and smoothing. Treat this as the more discriminating of the two — especially for
protocols heavy in digits, symbols, or case tricks. Because "stupid backoff" scores aren't
normalized probabilities, read it as a relative distance-from-English, not a calibrated one.

**How it's computed.** Same pipeline as `english_ngram_surprisal` (pristine text, per
character, per-message → per-round mean → run mean, deterministic, model cached in
`~/.cache/schmidt`), differing only in the trained vocabulary, case handling, and
backoff smoothing described above. Source:
`src/schmidt/evaluation/metrics/english_ngram/backoff_ngram_model.py`.

**Where to find it.** `run_level` and `message_level`.

---

## `message_entropy`

**What it is.** The Shannon entropy of the _characters within a single message_ — i.e. how
varied the symbols are. Reported in **bits per character**.

**The idea in depth.** Unlike the previous two, this metric is _not_ about prediction or about
English — it looks only at the message's own character mix. Take the message's character
frequencies (e.g. `aabb` → `a`: 50%, `b`: 50%) and compute Shannon entropy
`H = −Σ p(c)·log₂ p(c)`. `H` answers: "on average, how many bits would you need to encode each
character of this message, given how often each character appears in it?" Few distinct
characters (or one dominant character) → low entropy; many characters used evenly → high
entropy. It depends only on the _counts_ of characters, not their order — `abab` and `aabb`
have the same entropy.

**What the number means.** Lower = more repetitive / less internal variety. Extremes: a
message that is one repeated character (`LLLLLLL`) has a single symbol at 100% → **0 bits**
(perfectly uniform, no variety); ordinary English text uses many characters and lands around
**4–5 bits/char**. It is the simplest, most local "how much symbol diversity is in this
message" measure.

> **Worked micro-example.** `LLLLLLL` → one symbol → 0.00 bits. `12 twelve` → a handful of
> characters with uneven counts → moderate (~3 bits). A full English sentence → ~4.5 bits.

**How it's computed.**

- For each link message: count its character frequencies and compute `−Σ p(c)·log₂ p(c)`.
- Pristine text, scored per message, then per-round mean → run mean.
- Fully deterministic, model-free (no corpus, no network).
- Source: `src/schmidt/evaluation/metric_core/character_entropy.py` +
  `metrics/message_entropy_metric.py`.

**Where to find it.** `run_level` and `message_level`.

---

## `gzip_compression_ratio`

**What it is.** How compressible the message is, using gzip's compression algorithm
(DEFLATE). Reported as **compressed size ÷ original size**, in bytes.

**The idea in depth.** DEFLATE shrinks text by finding **repeated substrings** and rewriting a
repeat as a short back-reference ("copy 6 bytes from 9 bytes ago"). The more repetition and
structure a message has, the smaller the compressed output, so the ratio
`compressed_bytes ÷ original_bytes` is a direct, model-free measure of redundancy. This is
strictly richer than `message_entropy`: entropy only sees single-character frequencies, while
gzip also catches **multi-character** patterns — repeated words, repeated codes, `ABAB`
structure. So `Lf 12 Lf 12 Lf 12` looks very compressible to gzip (one repeated unit) even
though its character variety (entropy) is unremarkable.

**What the number means.** Lower = more compressible = more repetitive / lower information
density. Around or above 1 means the message barely compressed (varied, little internal
repetition).

> **Worked micro-example.** `Lf 12 Lf 12 Lf 12` → DEFLATE replaces the repeats with
> back-references → ratio well below 1. `gentle descent burn` → no exploitable repeats →
> ratio ≈ 1.

**Why the column has so many _identical_ values (and what that means).** The ratio is one
integer divided by another (`compressed_bytes ÷ original_bytes`). For the short messages on a
link channel those integers are small, so the ratio can only take a limited set of discrete
fractions — and **many different messages land on exactly the same value**. For example
`1.090909… = 24 ÷ 22`: every 22-byte message that DEFLATE cannot shrink compresses to 24 bytes
and therefore reports exactly `1.0909`. A repeated value like that is not a bug — it means
"these messages are all about the same short length and essentially incompressible (no
exploitable repetition), so DEFLATE returned the input size plus its small fixed per-stream
overhead." The signal is most meaningful in aggregate (run/round averages), not as an exact
per-message figure.

**How it's computed.**

- Each link message's pristine text (UTF-8 bytes) is compressed with **raw DEFLATE** at max
  level, and we take `compressed_bytes ÷ original_bytes`.
- **Why raw DEFLATE and not full gzip:** a gzip file carries a constant 18-byte header/footer.
  On short chat messages that fixed overhead dominates and would push the ratio above 1 for
  everything (a 7-byte message → ~25 bytes). We strip that constant framing (exactly:
  `raw_deflate_len == gzip_len − 18`), so the ratio reflects real compressibility and
  repetitive text correctly scores low.
- **Per message, not concatenated.** Each message is scored on its own (then per-round mean →
  run mean). We considered concatenating a whole round's messages before compressing — that
  would erase the overhead and also capture _cross-message_ repetition — but kept the
  per-message form for consistency with the other columns. (DEFLATE still has a small
  per-stream overhead, so very short messages can read well above 1.0 — a 1–2 character
  message compresses to ~3 bytes, giving ratios of 2–3 — while longer incompressible messages
  settle near 1.0.)
- Deterministic, model-free.
- Source: `src/schmidt/evaluation/metric_core/gzip_compression.py` +
  `metrics/gzip_compression_ratio_metric.py`.

**Where to find it.** `run_level` and `message_level`.

---

## `dialog_count` and `retransmission_request_count`

**What they are.** Two per-round counts of _communication overhead_ — link messages that
coordinate rather than carry new task content. They are produced by an LLM judge.

- `retransmission_request_count` — messages asking the partner to **repeat or resend**
  information that was lost or garbled (e.g. "say again", "resend the pressure value", or the
  protocol's coded equivalent). A direct symptom of the noisy channel.
- `dialog_count` — **clarification / coordination** back-and-forth that is _not_ transmitting
  new task data (asking for clarification, confirming/acknowledging receipt, coordinating
  turns). Pure retransmission requests are counted separately, not double-counted here.

**The idea in depth.** Unlike the four metrics above, this is not a formula over the
characters — it is a _classification count_. For each round, an LLM judge reads every
link message, decides which of the two buckets (if any) it falls into, and counts them. The
hard part is that the agents' protocol evolves into terse, coded shorthand, so a message is
often cryptic in isolation; a coded "resend" may have no question mark and look like noise. To
handle that, the judge is given the **whole run at once** — every round's link messages **and**
that round's postmortem-channel messages — and is told to use the postmortem debriefs and
earlier rounds as a "codebook" to decode each message's intent _before_ classifying it.

**What the number means.** Both are **average messages per round**. A `run_level`
`dialog_count` of `2.0` means each round contained, on average, about two clarification /
coordination messages; `0.5` means roughly one such message every two rounds. Higher = more of
the channel's budget spent on overhead rather than progress, so together they are a proxy for
how much friction the noise/protocol imposes. In the `round_context` sheet you see the count
for each individual round; in `run_level` you see the per-round average for the whole run.

**How they're computed.**

- An **LLM judge** (the project's standard `claude-haiku-4-5` evaluator) reads the run and
  counts, per round, how many link messages fall in each bucket.
- **Full context for decoding** (the entire run + postmortem channel), as described above, so
  the judge classifies by _decoded intent_, not by surface cues like question marks.
- **Pristine text**, judged round-by-round (not concatenated into one blob — counts stay
  per-round).
- **3 replicas, averaged.** To smooth the judge's run-to-run variability, the whole judging
  pass is run **three times** and the per-round counts are **averaged** across the three. This
  is why round-level counts can be fractional (e.g. `2.33` = the three passes saw 2, 3, 2).
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

- The four deterministic metrics are reproducible and free to recompute; the dialog /
  retransmission counts come from an LLM and will vary slightly if re-judged.
- `perplexity`, `english_ngram_surprisal`, `english_ngram_backoff_surprisal`,
  `message_entropy`, and `gzip_compression_ratio` all
  touch "how non-standard / compressible is the language," but via different mechanisms, so
  they are correlated yet **not** redundant (e.g. on baseline runs, perplexity vs.
  english-ngram correlate ~0.5 at the run level — related, but each adds signal).
- The dialog / retransmission counts measure something orthogonal: _conversational overhead_
  rather than the character-level shape of the text.
