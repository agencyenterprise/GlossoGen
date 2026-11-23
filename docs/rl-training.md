# Training a model with RL

You can train Qwen3.8-27B by reinforcement learning (RL) on signal_game with the code in
[modal/grpo/](../modal/grpo/README.md). The model plays both seats of each game, and each player
gets a score of 0 or 1 in each round. A trainer then updates a LoRA adapter, a small set of
weights added to the model. A player's answers in a round become more likely when its score is
above the mean score of its seat in that round, over the games played on the same seed. They
become less likely when its score is below that mean.

The commands for a ten-step run on the `first_item` reward, and its evaluation:

```bash
export GRPO_APP_NAME=grpo-<your name>
VIRTUAL_ENV= uv run --no-sync modal deploy modal/grpo/grpo_app.py
VIRTUAL_ENV= uv run --no-sync python modal/grpo/grpo_loop.py init --app $GRPO_APP_NAME --run first-item
VIRTUAL_ENV= uv run --no-sync python modal/grpo/grpo_loop.py train --app $GRPO_APP_NAME \
  --run first-item --runs-dir runs --records-dir ~/grpo-records \
  --game-config modal/grpo/signal_game_shapes.json --concurrency 12 \
  --first-step 0 --last-step 9 --reward first_item --seeds-per-step 4 --games-per-seed 6
VIRTUAL_ENV= uv run --no-sync python modal/grpo/grpo_loop.py eval --app $GRPO_APP_NAME \
  --run first-item --runs-dir runs --records-dir ~/grpo-records \
  --game-config modal/grpo/signal_game_shapes.json --concurrency 12 \
  --step 10 --games-per-seed 6 --seeds 42 43 44
VIRTUAL_ENV= uv run --no-sync modal app stop $GRPO_APP_NAME --yes
```

Run them from the repository root. For the base model's score on the same seeds, run `eval` again
with `--step 0`. `grpo_loop.py` is the loop that plays the games and sends each batch to the
trainer, and it runs on your machine. Keep the machine awake while `train` runs.

| Run | Time per training step | Ten steps |
| --- | --- | --- |
| The run under [What to expect](#what-to-expect), 20 Nov 2026 | 15 to 24 minutes | 3.2 hours |
| Another ten-step run on `first_item`, 19 Nov 2026 | 33 to 59 minutes | 7.3 hours |
| Step 0 under [What a step prints](#what-a-step-prints), 23 Nov 2026 | 40.5 minutes | |

## What you need

| Need | How |
| --- | --- |
| The modal CLI | it comes with `make install` |
| A Modal account, with the CLI authenticated | `modal token new` |
| The secrets `huggingface-glossogen` and `vllm-api-key` | [Self-hosted models](local-inference-vllm-mlx.md#one-time-setup) |
| `SELF_HOSTED_API_KEY` in `.env`, equal to the secret's `VLLM_API_KEY` | [Self-hosted models](local-inference-vllm-mlx.md#wire-glossogen-to-it) |
| GPUs on Modal: a B200 or an H200 for the trainer, an H200 or an H100 for the policy server | your workspace's GPU access |
| A name for the app that nobody in your Modal workspace uses | `modal app list` |

The policy server is the vLLM server in the app. `GRPO_APP_NAME` is the name of the app and of
its volume. The loop asks the policy server to load an adapter through a Modal Dict named
`<GRPO_APP_NAME>-adapters`. The model weights come from the shared `huggingface-cache` volume, as
for the [serving apps](../modal/README.md), and a first start downloads them if they are not
there. signal_game has no LLM judge, so the games need no provider key other than the
self-hosted one.

## How one training step works

In step k, the loop and the trainer do the following:

1. The policy server loads adapter k and serves it as the model `<run>-step<k>`. The policy is
   the model with its current adapter. Adapter 0 leaves the base model's outputs unchanged. The
   loop waits until the policy server reports that the adapter is loaded.
2. The loop plays 6 games on each of the step's 4 seeds. With `--seeds-per-step 4`, step k plays
   seeds 1000 + 4k to 1003 + 4k. The policy plays both seats of every game at temperature 1.0, so
   the 6 games of a seed differ. Every game runs with `record_token_ids=true`, so its event log
   holds the token ids of every prompt and answer.
3. The reward gives each player a score of 0 or 1 in each round. A player's advantage in a round
   is its score minus the mean score of its seat in that round, over the seed's finished games.
4. The loop reads each player's prompts and answers from the logged token ids, and marks every
   answer token with the advantage of its round. An answer's round is the round of its first
   tool call. An answer without a tool call takes the round of the player's previous call, and an
   answer before the player's first call gets advantage 0.
5. The trainer takes one gradient step on these sequences and saves adapter k+1.

### The loss

This method is GRPO (group relative policy optimization). Its group is the set of finished games
of one seed. The advantage is not divided by the group's standard deviation, as some versions of
GRPO do. The loss of each answer token is `-advantage × log p_policy(token) + 0.02 × k3`, averaged
over the batch's answer tokens.

k3 estimates the KL divergence between the policy and the base model on that token. The KL
divergence measures how far one model's token probabilities are from another's. With
r = log p_base − log p_policy, k3 = exp(r) − r − 1, capped at 10. k3 is 0 when the two models give
the token the same probability, and it grows as the two probabilities differ. The `kl` that each
step prints is the mean k3 over the batch's answer tokens.

When a seat scored the same in a round in every finished game of a seed, that seat's advantage in
that round is 0. Only the k3 term then acts on that seat's answer tokens from that round. A game
that ends without `simulation_ended` is left out of the batch.

## Settings and records

| Setting | Where |
| --- | --- |
| LoRA rank 32 and alpha 64, learning rate 1e-4, k3 weight 0.02, gradient norm clipped at 1.0 | `SETTINGS` in `grpo_app.py`. The trainer uses the deployed settings. `init` also saves them as `runs/<run>/settings.json` on the volume |
| Seeds per step, games per seed, games at a time | the `train` and `eval` flags |
| Grid, items, rounds, temperature | the game config, `signal_game_shapes.json` |

Each game's event log lands in `--runs-dir`, under `signal_game/`. A training game's labels are
`grpo`, `reward=<reward>`, `run=<run>`, `step=<k>`, `seed=<seed>` and `game=<n>`. An evaluation
game's labels are the same without `reward=`, and with `grpo_eval` in place of `grpo`. Ten steps
and one evaluation at the sizes above make 258 run directories. The loop's own records are in
`<records dir>/<run>/`:

| Path | What it holds |
| --- | --- |
| `steps.jsonl` | one line per training step |
| `eval.jsonl` | one line per evaluation: the rounds won, and the first-item finishes out of the player-rounds |
| `configs/` | each seed's game config |
| `game_logs/` | the terminal output of each `glossogen run`, named `<label>_step<k>_seed<seed>_game<n>.log` |

### Resuming after a stop

The adapters are on the volume, at `runs/<run>/adapters/step_<k>/`. To resume, find the highest k
for which that folder exists, and run `train` with `--first-step k`. The trainer then loads
adapter k from the volume. The loop refuses to play a game whose log is already in `game_logs/`.
To run a step again after it stopped partway, first move that step's logs out of `game_logs/`.
`steps.jsonl` then gets a second line for that step.

## Rewards

[signal_game_rewards.py](../modal/grpo/signal_game_rewards.py) defines the rewards that `--reward`
accepts:

| `--reward` | A player scores 1 in a round when |
| --- | --- |
| `win` | the round was won: both players ended on the same item |
| `first_item` | the player ended on the alphabetically first item of its own grid |

A player can score on `first_item` whatever its partner does. Train on `first_item` before `win`,
to check that training changes where the players end their rounds.

### Another scenario

To train on another scenario, write a module like `signal_game_rewards.py`. It reads a run's
events and gives each agent a score in each round. `grpo_loop.py` imports `Reward`,
`PlayerRound`, `GameOutcome`, `game_outcome` and `player_score` from that module. It reads the
`GameOutcome` fields `finished`, `players`, `rounds`, `won_rounds`, `first_item_finishes`, `moves`
and `player_rounds_without_move`. Your module has to provide all of them, or `grpo_loop.py` has
to change. Set `SCENARIO` in `grpo_loop.py` to the scenario's name, and pass its config as
`--game-config`. The policy has to play every agent of the game, because the policy server
serves one adapter under one name.

## What a step prints

On 23 Nov 2026, the `train` command above ran with `--run tutorial-check` and `--last-step 0`. It
ran on an earlier revision of `grpo_loop.py`, which differed in its docstrings and in how it
looked up the policy server's URL. Its output held these two lines:

```
loaded tutorial-check-step0
step 0: 24/24 games finished, won 23/240 rounds, first item 89/480 player-rounds, 2148 answers (191330 tokens), kl 0.00000, grad norm 0.0130, play 1865s, train 567s
```

A player-round is one player in one round. The 191,330 tokens are the answer tokens of the 2,148
answers. The KL is 0 at step 0, because adapter 0 leaves the base model unchanged. Loading
adapter 0, playing the 24 games and building the batch took 31 minutes, the record's
`play_seconds`. Sending the batch and training took 9.5 minutes, the record's `train_seconds`.
The trainer's own step took 8.5 of them, `trainer.seconds`.

`steps.jsonl` also holds the rounds won in each game of each seed, the moves per player-round,
and the trainer's metrics. `trainer.marked_tokens` counts the answer tokens, and
`trainer.advantaged_tokens` counts those with a nonzero advantage: 124,189 of 191,330 in this
step.

### Retried requests

Modal answers HTTP 303 to a request that has run for 150 seconds. After a 303, GlossoGen sends the
request again, up to 3 attempts, and then restarts the agent's turn. Counting each attempt, the
step sent 2,156 requests. 8 got a 303, and the other 2,148 got an answer. One agent's turn got a
303 on all 3 attempts, and the runner restarted it. Its game still finished. An answer that takes
more than 150 seconds to generate gets a 303 on every attempt, so no such answer reaches the
batch.

## What to expect

The table comes from one ten-step run on 20 Nov 2026. That run used an earlier version of
`grpo_loop.py`, with another command line. A proxy, a program between the games and vLLM,
recorded the token ids of each request. The run used the same seeds, flag values and trainer
settings as the commands above, and the same game config without `record_token_ids`. The
held-out seeds, 42 to 44, are seeds that no training step plays.

| Games | Ended on the first item | Random square | Start square |
| --- | --- | --- | --- |
| Step 0, seeds 1000 to 1003, the base model | 83 of 480 | 83 | 84 |
| Steps 8 and 9, seeds 1032 to 1039 | 210 of 960 | 161 | 192 |
| Held-out seeds 42 to 44, adapter 10 | 96 of 360 | 67 | 96 |
| Held-out seeds 42 to 44, the base model | 65 of 360 | 67 | 96 |

### The baselines

The two baseline columns count the player-rounds that would end on the first item. The
random-square count is the expected count when each player ends on a random square of its grid.
A grid can hold its first item on more than one square, because each square's item is drawn on
its own. The start-square count is the count when each player stays on its start square. Both
counts depend on the seeds' boards, so they differ from step to step.
[first_item_baselines.py](../modal/grpo/first_item_baselines.py) prints them for each step:

```bash
VIRTUAL_ENV= uv run --no-sync python modal/grpo/first_item_baselines.py \
  --game-config modal/grpo/signal_game_shapes.json --games-per-seed 6 \
  --last-step 9 --seeds-per-step 4 --held-out-seeds 42 43 44
```

### During training

At step 0, the base model ended on the first item in 83 of 480 player-rounds, and the
start-square baseline was 84. At steps 8 and 9, the policy ended on it in 210 of 960, and the
start-square baseline was 192. Across steps 0 to 9, the start-square baseline ranges from 42 to
108 of 480, so compare each step with its own baselines.

Six runs have played step 0 on seeds 1000 to 1003 with the base model. They ended on the first
item in 79, 83, 84, 85, 89 and 93 of 480 player-rounds, so two runs of the same model on the same
seeds can differ by 14. In the training steps of the table's run, the player-rounds without a
move went from 120 of 480 at step 0 to 89 of 480 at step 9. The moves per player-round stayed
between 1.6 and 1.9.

### On the held-out seeds

Adapter 10 ended on the first item in 96 of 360 player-rounds, and the base model in 65. The
start-square baseline is 96. The evaluation does not count moves. Each count comes from one
evaluation of 18 games. The base model's count comes from the evaluation of adapter 0 in a `win`
run on 18 Nov 2026.

On the same seeds, other adapters ended on the first item in these numbers of player-rounds:

| Adapter | Ended on the first item |
| --- | --- |
| Trained on `first_item` for 10 steps, on prompts rebuilt from the log's text | 104 of 360 |
| Trained on `win` for 10 steps | 85 of 360 |
| Trained on `win` for 12 steps | 91 of 360 |

## Before a long run

**Train on the logged token ids, never on prompts rebuilt from the log's text.** The loop refuses
a game config without `record_token_ids`. On 20 Nov 2026, the 2,223 prompts of one step were
rebuilt from the event log's text, with the tools in the order that the model receives them.
240 of the 2,223 rebuilt prompts differed from vLLM's prompts. 10 of the 48 players had a move
refused. The model received each refusal's error as JSON, and the log holds it as plain text.

**Before you train on a new reward, check how many answer tokens get a nonzero advantage.** An
answer token with advantage 0 changes the adapter only through the k3 term. Step 0's line in
`steps.jsonl` holds `trainer.advantaged_tokens` and `trainer.marked_tokens`. At step 0 on these
seeds, 45% and 51% of the answer tokens had a nonzero advantage under `win`, in two runs. Under
`first_item`, 58% to 65% had one, in four runs.

The two `win` runs won 20 of 180 held-out rounds after 10 steps and 19 after 12 steps, and the
base model won 22. On those seeds, players who stay on their start squares would win 24 of 180,
and players who end on random squares would win 20. Both runs trained on prompts rebuilt from the
log's text, and the 12-step run used learning rate 2e-5.

**Keep the policy server on an H200 or an H100.** On 18 Nov 2026, with LoRA on, vLLM 0.31 failed
twice while capturing CUDA graphs: once on a B200, and once on a GPU whose type was not recorded.
The app's `serve` function asks for an H200 or an H100.

**Stop the app when you finish.** The policy server keeps one GPU running until `modal app stop`,
even when no game is playing. The trainer stops 20 minutes after its last call. When a step's
games take longer than that, the next step starts a new trainer, which loads the adapter from the
volume. Stopping the app keeps the volume and the Dict. `modal volume delete` and
`modal dict delete` remove them.

**Check the volume before you run `init` again.** `init` refuses a run that already exists on the
volume. An `init` call can create the run even when your terminal shows an error. If
`modal volume ls $GRPO_APP_NAME runs/<run>/adapters` lists `step_0`, go on with `train`.

**If `train` ends before `--last-step`, read its line that starts with `stopping:`.** The loop
stops after a step whose KL is above 0.3. It also stops after a step in which fewer than 75% of
the started games finished. Neither number counts a game that failed before `glossogen run`
printed its run id.

## Where to go next

- [Running simulations](running-simulations.md#self-hosted-and-local-models) explains
  `record_token_ids` and the self-hosted provider.
- [Reading runs from code](reading-runs-from-code.md) covers the event log, which
  `signal_game_rewards.py` reads.
- [modal/grpo/README.md](../modal/grpo/README.md) lists the files and how to run their tests.
