# Designs for two features that the loop does not have

This page describes two changes to the code in this folder. Neither is built. The first gives each
seat its own trained adapter. The second starts a new game in each free game slot, as platoon
does. [Training a model with RL](../../docs/rl-training.md) describes the loop as it is.

## A trained adapter for each seat

In a run without a partner, one adapter plays both seats and trains on both seats' answers. In
this design, each seat has its own adapter and its own optimizer. Platoon calls this "several
policies trained in lockstep" and marks it experimental.

### The trainer

- `with_lora` adds two named adapters to the base model with PEFT's `add_adapter`, one for
  `player_a` and one for `player_b`. Each adapter gets its own AdamW optimizer.
- `train_step` takes the sequences of each seat apart, for example as a list of
  `SeatBatch(seat, sequences)` records. For each seat, it makes that seat's adapter the active
  one with `set_adapter`, runs the loss on that seat's sequences, clips that adapter's gradient
  and steps its optimizer. The reference logprobs come from `disable_adapter()`, as they do now.
- The trainer saves both adapters under `runs/<run>/adapters/step_<k>/<seat>/`, with their
  optimizer states and one set of metrics for each seat.
- `initialize` creates both adapters with B = 0, so both seats start as the base model. The
  run's `settings.json` lists the trained seats.
- The token count per step does not change: each seat's pass covers that seat's answers only.
  The optimizer state doubles, and it holds the LoRA parameters only.

### The policy server's loader

- An `AdapterRequest` names one adapter for each seat, under `<run>-<seat>-step<k>`, and the
  loader loads both before it writes its result.
- vLLM's `--max-loras` limits the adapters in one batch. One version takes 2 slots. With
  `--overlap`, two versions are loaded at once, which takes 4 slots. Each slot reserves GPU
  memory for an adapter of the maximum rank, so the H100 setting of `--gpu-memory-utilization
  0.85` needs a check.

### The loop

- Each seed config gives each seat its own model in `model_overrides`: `<run>-<seat>-step<k>`
  under `self-hosted`. `SELF_HOSTED_BASE_URLS` maps both names to the policy server.
- A frozen partner replaces one seat's adapter. The partner file and `trained_seats` stay as they
  are.
- `batch` groups the sequences by seat, and the trainer gets one group for each seat.
- Each seat's advantage is computed as it is now: its score minus its seat's mean in the round,
  over the seed's finished games.
- `steps.jsonl` records the trainer's metrics for each seat. The KL stop applies when either
  seat's KL is above 0.3.
- The ledger and the resume logic do not change. The `adapter` of a game is the step of the
  adapters that played it.

## Starting a game in each free slot

Today, a step's games start together, `--concurrency` at a time, and the step ends when its
slowest game ends. Slots whose game has ended wait for that slowest game. With `--overlap`, the
next step's games start when the trainer has saved the next adapter and the current step's
games have ended. Platoon starts a new game in a slot as soon as the slot's game ends. It bounds
how far the games run ahead of training with `max_staleness`: at most `max_staleness + 1`
batches have started and are not trained.

In the platoon spike, the 12 slots were busy 68% of each step's play window, from 51% to 86%
across steps. That measurement is in
`~/Documents/rl-training-artifacts/platoon-spike/FINDINGS.md`. It assumes that games run as fast
when every slot is busy, which the spike did not check.

### The scheduler

- A `GameScheduler` owns the `--concurrency` slots and a queue of game specs across steps:
  step k's games, then step k+1's. Each slot takes the next spec as soon as its game ends.
- A game plays the newest adapter when it starts, not the adapter of its step. The ledger
  already records each game's adapter.
- With a bound S, the scheduler does not start a game of step k + S + 1 before the trainer has
  trained step k. With S = 1, at most 2 steps have games that have started and are not trained.
- The trainer trains step k when all of step k's games have ended. A step's advantages need all
  the finished games of each seed, as they do now.

### Adapters on the policy server

- The adapters to keep are those that a running game plays, and the newest one. With S = 2,
  games of adapters k−2, k−1 and k can be running at once, so the server holds up to 3 adapters.
  vLLM's `--max-loras` then has to be at least 3.
- The scheduler sends a load request when the trainer saves an adapter, and a request that
  keeps one adapter fewer when the last game of an old adapter ends.

### The batch and the loss

- One step's games can come from up to S + 1 adapters. The importance weight uses each token's
  logged logprob, so it handles a batch from several adapters. The cap of 5 limits the weight of
  a token from an old adapter.
- The advantage baseline of a seed then mixes games of different adapters. Platoon can drop
  each datum that is older than the bound. This loop would drop each game that is more than S
  adapters older than the trainer, and record the count of dropped games in `steps.jsonl`.

### Resume and records

- The ledger already holds each ended game's adapter. A resumed run plays each cut-off game
  with the newest adapter. The check that refuses a step whose games another adapter played
  becomes a check that each game is within S adapters of the step.
- `steps.jsonl` records, for each step, the number of games that each adapter played.
- The tests in `test_grpo_steps.py` would need a fake trainer that takes time, so that games of
  two steps run at once. A fake clock, which the test advances, would keep them free of
  wall-clock waits.
