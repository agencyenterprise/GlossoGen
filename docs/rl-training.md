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
  --step 10 --games-per-seed 6 --seeds $(seq 45 56)
VIRTUAL_ENV= uv run --no-sync modal app stop $GRPO_APP_NAME --yes
```

Run them from the repository root. For the base model's score on the same seeds, run `eval` again
with `--step 0`. `grpo_loop.py` is the loop that plays the games and sends each batch to the
trainer, and it runs on your machine. Keep the machine awake while `train` runs.

| Runs under [What to expect](#what-to-expect) | Time per training step | Ten steps |
| --- | --- | --- |
| `tutorial-check`, with none of the other three runs' apps running | 15.9 to 40.5 minutes | 3.7 hours |
| `first-item-rep1` to `first-item-rep3`, while the other two of these runs and one evaluation app ran | 13.3 to 39.0 minutes | 3.6 to 4.4 hours |

The first step includes the policy server's start. Steps 10 to 29 of `first-item-rep3` took 20.7
to 48.4 minutes each. An evaluation of 72 games took 30 to 50 minutes.

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
and one evaluation at the sizes above make 312 run directories. The loop's own records are in
`<records dir>/<run>/`:

| Path | What it holds |
| --- | --- |
| `steps.jsonl` | one line per training step |
| `eval.jsonl` | one line per evaluation: the rounds won and the player-rounds that ended on the first item, for each game grouped by seed, and in total |
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

The commands above ran four times from 23 to 25 Nov 2026, as the runs `tutorial-check`,
`first-item-rep1`, `first-item-rep2` and `first-item-rep3`. `first-item-rep3` ran them with
`--last-step 19` and then continued training to step 29. The learning rate does not depend on the
last step, so its steps 0 to 9 used the same settings as a ten-step run.

A run's count is the number of player-rounds that ended on the first item. A run learned when its
count over steps 5 to 9 was more than 54 above the base model's count. 54 is twice the standard
deviation of the difference between two such counts (see
[How much the counts vary by chance](#how-much-the-counts-vary-by-chance)). Two of the four runs
learned within ten steps. Adapter 10 is the adapter after step 9.

| Run | Steps 5 to 9, of 2,400 player-rounds | Adapter 10 on seeds 45 to 56, of 1,440 |
| --- | --- | --- |
| `first-item-rep1` | 536 | 322 |
| `first-item-rep2` | 523 | 309 |
| `first-item-rep3` | 422 | 246 |
| `tutorial-check` | 419 | 221 |
| The base model | 445 | 234, 256, 266 and 257 |

A run's count for each step is `first_item` in its `steps.jsonl`. Steps 5 to 9 play seeds 1020 to
1039. The base model's 445 is its count on those seeds, in one evaluation of `tutorial-check`'s
adapter 0 (see [During training](#during-training)). No training step plays seeds 45 to 56, and each
count on them comes from one evaluation of 72 games. The base model's counts there are adapter 0 of
`tutorial-check` (234), `first-item-rep1` (256), `first-item-rep2` (266) and `first-item-rep3`
(257).

Runs of the same commands differ because no random seed is fixed for them. The policy samples
every answer at temperature 1.0. The trainer draws the adapter's A matrices at random and sets its
B matrices to 0. So adapter 0 leaves the base model's outputs unchanged, but the later adapters
depend on the A matrices.

### How much the counts vary by chance

Two evaluations of the same model on the same seeds give different counts. The binomial standard
deviation treats each player-round as an independent draw. For a count near 445 of 2,400, it is
about 19, and the difference of two such counts has a standard deviation of about 27. For a count
near 250 of 1,440, these are about 14 and 20. The player-rounds of one game share its grids and its
history, so the binomial value can understate the spread.

The base model has played seeds 1000 to 1003 five times: at step 0 of each of the four runs, and in
the evaluation of adapter 0. Those five counts, each out of 480 player-rounds, have a standard
deviation of 8.5, and the binomial value is 8.1. On these seeds the two values are close, though
five counts give only a rough estimate. Twice the standard deviation of a difference is about 54 for
steps 5 to 9 and about 40 on seeds 45 to 56.

| Run | Steps 5 to 9, minus the base model | Adapter 10 minus its own adapter 0, on seeds 45 to 56 |
| --- | --- | --- |
| `first-item-rep1` | +91 | +66 |
| `first-item-rep2` | +78 | +43 |
| `first-item-rep3` | −23 | −11 |
| `tutorial-check` | −26 | −13 |

### Training longer

`first-item-rep3` ran `train` with `--last-step 19`, and then with `--first-step 20 --last-step 29`,
which resumes from adapter 20 on the volume. Over steps 10 to 19, its players ended on the first
item in 69 to 122 of 480 player-rounds per step. Over steps 20 to 29, they did so in 126 to 210.

On the grids of steps 10 to 29, players who ended on random squares would end on the first item in
76 to 95 per step, and players who stayed on their start squares in 42 to 126 (see [Random-square
and start-square baselines](#random-square-and-start-square-baselines)). Steps 10 to 29 took 9.5
hours.

On seeds 45 to 56, the players of adapter 20 ended on the first item in 346 of 1,440 player-rounds,
and those of adapter 30 in 632. With the run's adapter 0, they did so in 257. This is one run, so it
does not show how often a run learns within 30 steps.

### Rounds won after training longer

With adapter 30, the players won 131 of 720 rounds, and with adapter 0, 88. Both players ended on
a blue circle in 74 of those 131 rounds, and in 10 of the 88 rounds won with adapter 0.

A round is won when both players end on the same item. The blue circle is the first item of any grid
that holds one. So when both grids hold a blue circle, two players who each end on their first item
end on the same item.

### What `first_item` rewards

Each item is a colour and a shape, such as `blue star`. The game config uses the colours red, blue
and green, and the shapes circle, triangle and star. A grid's alphabetically first item is
therefore a blue item whenever the grid holds one. Each square's item is drawn independently from
the 9 items, with repeats allowed, so a grid of 9 squares holds no blue item with probability
(2/3)^9, about 3%.

A player scores 1 when it ends a round on a square that holds its grid's first item, such as
`blue circle`. A blue item of another shape on the same grid does not score.

### During training

Step k plays seeds 1000 + 4k to 1003 + 4k, so the grids change from step to step. Compare each
step with the base model on the same seeds. The base model's column below comes from one
evaluation of adapter 0 on the training seeds:

```bash
VIRTUAL_ENV= uv run --no-sync python modal/grpo/grpo_loop.py eval --app $GRPO_APP_NAME \
  --run first-item --runs-dir runs --records-dir ~/grpo-records \
  --game-config modal/grpo/signal_game_shapes.json --concurrency 12 \
  --step 0 --games-per-seed 6 --seeds $(seq 1000 1039)
```

`first_item_by_seed` in `eval.jsonl` holds each game's count. A step's count is the sum over its
four seeds. The 240 games took 1.7 hours.

| Step | Base model | `first-item-rep1` | `first-item-rep2` | `first-item-rep3` | `tutorial-check` |
| --- | --- | --- | --- | --- | --- |
| 0 | 68 | 76 | 74 | 85 | 89 |
| 1 | 79 | 74 | 88 | 80 | 72 |
| 2 | 85 | 77 | 76 | 87 | 71 |
| 3 | 77 | 89 | 93 | 89 | 87 |
| 4 | 97 | 111 | 101 | 100 | 89 |
| 5 | 77 | 72 | 94 | 67 | 65 |
| 6 | 89 | 115 | 94 | 74 | 83 |
| 7 | 98 | 120 | 117 | 111 | 106 |
| 8 | 94 | 128 | 120 | 90 | 91 |
| 9 | 87 | 101 | 98 | 80 | 74 |

Each count is out of 480 player-rounds. Every run plays adapter 0 at step 0, so the five counts of
step 0 all come from the base model. They range from 68 to 89.

A player-round without a move is one in which the player made no move, so it ended the round on
its start square. The two runs that did not learn within ten steps had more of them. Over steps 5
to 9, `tutorial-check` and `first-item-rep3` averaged 136 and 116 per step. `first-item-rep1` and
`first-item-rep2` averaged 102 and 105. With two runs in each group, this does not show that these
player-rounds predict learning. `steps.jsonl` holds the count as `player_rounds_without_move`.

### Random-square and start-square baselines

[first_item_baselines.py](../modal/grpo/first_item_baselines.py) prints two counts of
player-rounds that end on the first item, one line per step. The first is the expected count if
each player ended on a random square. The second is the count if each player stayed on its start
square. Summed over steps 5 to 9, its lines give 396 and 432. On seeds 45 to 56, the counts are
241 and 216.

```bash
VIRTUAL_ENV= uv run --no-sync python modal/grpo/first_item_baselines.py \
  --game-config modal/grpo/signal_game_shapes.json --games-per-seed 6 \
  --last-step 9 --seeds-per-step 4 --held-out-seeds $(seq 45 56)
```

### Runs with the `win` reward

Before the four runs above, two runs trained with the `win` reward, for 10 and 12 steps. Neither won
more rounds than the base model. On seeds 42 to 44, which no training step plays, the 10-step run
won 20 of 180 rounds, the 12-step run won 19, and the base model won 22. On those seeds, players who
stay on their start squares would win 24 of 180, and players who end on random squares would win 20.

The 10-step run used learning rate 1e-4, and the 12-step run 2e-5. Both trained on prompts rebuilt
from the log's text, so they do not show whether `win` can train the model on logged token ids.

## Before a long run

**Before you start another run, compare yours with the base model.** If your run's count over
steps 5 to 9 is not more than 54 above 445, continue training it with
`--first-step 10 --last-step 29`, as in [Resuming after a stop](#resuming-after-a-stop). Two of the
four runs under [What to expect](#what-to-expect) did not learn in ten steps. One of them continued
training to step 29. On seeds 45 to 56, its players ended on the first item in 632 of 1,440
player-rounds with adapter 30, and in 257 with adapter 0 (see [Training longer](#training-longer)).

That run ran steps 10 to 29 in two commands, and one command runs the same steps. Its steps 10 to 29
took 9.5 hours. A new ten-step run took 3.6 to 4.4 hours, and 2 of 4 runs learned within ten steps.

**Train on the logged token ids, never on prompts rebuilt from the log's text.** The loop refuses
a game config without `record_token_ids`. On 20 Nov 2026, the 2,223 prompts of one step were
rebuilt from the event log's text, with the tools in the order that the model receives them. Even
so, 240 of the 2,223 rebuilt prompts differed from vLLM's prompts. One cause is a refused move: 10
of the 48 players had one. The model received each refusal's error as JSON, and the log holds it as
plain text, so each later prompt of those players differed.

**Before you train on a new reward, check that answer tokens get a nonzero advantage.** An answer
token with advantage 0 changes the adapter only through the k3 term. The share of answer tokens with
a nonzero advantage is `trainer.advantaged_tokens` divided by `trainer.marked_tokens`, in step 0's
line in `steps.jsonl`. A share near 0 means that the reward gives nearly every player of a seed the
same score.

At step 0 on seeds 1000 to 1003, 45% and 51% of the answer tokens had a nonzero advantage in the two
`win` runs. Under `first_item`, 41% to 65% had one, in seven runs: the four under [What to
expect](#what-to-expect) and three earlier runs. Within that range, the share did not tell which
runs would learn: `first-item-rep2` had 41% and learned, and `tutorial-check` had 65% and did not.

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
