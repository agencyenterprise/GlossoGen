# Designs for two features that the loop does not have

Neither design below is built. The first gives each seat its own trained adapter. The second
starts the next step's games in game slots that free up before the current step ends, as the
platoon RL library does. [Training a model with RL](../../docs/rl-training.md) describes the loop.

## A trained adapter for each seat

In a run without a partner, one adapter plays both seats and trains on both seats' answers. In
this design, each seat has its own adapter and its own optimizer. Platoon calls this "several
policies trained in lockstep" and marks it experimental.

### The trainer

- `with_lora` adds two named adapters to the base model with PEFT's `add_adapter`, one for
  `player_a` and one for `player_b`. Each adapter gets its own AdamW optimizer.
- `train_step` receives each seat's sequences separately, as a list of
  `SeatBatch(seat, sequences)` records. For each seat, it makes that seat's adapter the active
  one with `set_adapter`, and runs the loss on that seat's sequences. It then clips that
  adapter's gradient and steps that adapter's optimizer. The reference logprobs come from
  `disable_adapter()`, as in the loop.
- The trainer saves both adapters under `runs/<run>/adapters/step_<k>/<seat>/`, each with its
  optimizer state and its own metrics.
- `initialize` creates both adapters with their LoRA B matrices at 0, so both seats start as the
  base model. The run's `settings.json` lists the trained seats.
- The answer tokens per step stay the same, because each seat's pass covers that seat's answers
  only. The optimizer state doubles, and it holds the LoRA parameters only.

### The policy server's loader

- An `AdapterRequest` names one adapter for each seat, under `<run>-<seat>-step<k>`. The loader
  loads both before it writes its `AdapterResult` into the control Dict.
- vLLM's `--max-loras` limits how many adapters run in one batch. The two adapters of one step
  need 2 of these LoRA slots. With `--overlap`, the adapters of two steps are loaded at once, 4
  in all. vLLM sizes its LoRA buffers by `--max-loras` and `--max-lora-rank`. On an H100, the
  server runs with `--gpu-memory-utilization 0.85`, and nobody has checked that 4 LoRA slots fit.

### The loop

- Each seed config gives each seat its own model in `model_overrides`: the model
  `<run>-<seat>-step<k>`, under the provider `self-hosted`. `SELF_HOSTED_BASE_URLS` maps both
  names to the policy server.
- A frozen partner replaces one seat's adapter. The partner file and the steps' `trained_seats`
  field keep their form.
- `batch` groups the sequences by seat, and the trainer gets one group for each seat.
- Each seat's advantage is its score minus its seat's mean score in the round, over the seed's
  finished games, as in the loop.
- `steps.jsonl` records the trainer's metrics for each seat. Training stops after a step in which
  either seat's `kl`, its mean k3 per answer token, is above 0.3.
- `games.jsonl`, the ledger of ended games, and the resume logic keep their form. A game's
  `adapter` field holds k when the two adapters k played it.

## Starting the next step's games in free game slots

A game slot is one of the `--concurrency` games that play at once. A step's games play
`--concurrency` at a time, and each game starts when a game slot frees. Once no game of the step
is left to start, a game slot that frees waits until the step's slowest game ends. With
`--overlap`, step k+1's games start once the trainer has saved adapter k and all of step k's
games have ended. Platoon starts a new game in a slot as soon as the slot's game ends, a game of
the next batch included. Its `max_staleness` setting bounds how far the games run ahead of
training: at most `max_staleness + 1` batches have games that started and are not trained.

The platoon spike measured the game slots in the 60 steps of the 4 runs that
[Our runs](../../docs/rl-training.md#our-runs) lists. A step's play window lasts from its first
game's start to its last game's end. The 12 game slots were busy 68% of the play window on
average, and from 51% to 86% in single steps. These numbers are in
`~/Documents/rl-training-artifacts/platoon-spike/FINDINGS.md`, outside the repository, and the
repository holds no script that computes them. Filling the idle slots saves time only if games
play as fast when every slot is busy. Nobody has checked that.

### The scheduler

- A `GameScheduler` owns the game slots and a queue of game specs across steps: step k's games,
  then step k+1's. Each slot takes the next spec as soon as its game ends.
- Each game plays the newest adapter at the time that it starts. `games.jsonl` already records
  each game's adapter.
- With a bound S, the scheduler does not start a game of step k + S + 1 before the trainer has
  trained step k. S plays the role of platoon's `max_staleness`. A game of step j then plays
  adapter j − S or a newer one, so no game is more than S adapters older than the adapter that
  the trainer starts step j from.
- The trainer trains step k when all of step k's games have ended. A step's advantages need all
  the finished games of each seed, as in the loop.

### Adapters on the policy server

- The loop keeps loaded each adapter that a running game plays, and the newest adapter. With
  S = 2, games of adapters k−2, k−1 and k can be running at once, so the server holds up to 3
  adapters. vLLM's `--max-loras` then has to be at least 3.
- The scheduler sends a load request when the trainer saves an adapter. It sends a request that
  leaves an old adapter out of `keep` when the last game that plays that adapter ends.

### The batch and the loss

- One step's games can come from up to S + 1 adapters. The importance weight uses each token's
  logged logprob, so it handles a batch from several adapters. Its cap of 5 limits the weight of
  a token from an older adapter.
- Each advantage subtracts the seat's mean score in the round. With this design, that mean mixes
  games of different adapters.

### Resume and records

- When a run resumes, the loop plays each game that was playing at the stop again, with the
  newest adapter. The check that refuses a step whose games another adapter played becomes a
  check that each game's adapter is at most S older than the step's.
- `steps.jsonl` records, for each step, the number of games that each adapter played.
- `test_grpo_steps.py` would need a fake trainer that finishes only when the test advances a fake
  clock. Games of two steps then run at once, and no test waits on wall-clock time.
