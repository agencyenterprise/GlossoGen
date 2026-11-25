# Training a model with RL

These steps train Qwen3.8-27B by reinforcement learning (RL) on signal_game, with the code in
[modal/grpo/](../modal/grpo/README.md). In signal_game, two players each have their own grid of
squares, and each square holds an item, such as `blue star`. Each player starts a round on a square
of its own grid and moves to another. The two places in a game are its seats, player_a and
player_b. A ten-step run took 3.6 to 4.4 hours on Modal, and testing
it took 1 to 1.5 hours more.

| Step | Command | Time in our runs |
| --- | --- | --- |
| [1. Deploy the app](#1-deploy-the-app) | `modal deploy` | under a minute |
| [2. Create the run](#2-create-the-run) | `grpo_loop.py init` | about a minute |
| [3. Train for ten steps](#3-train-for-ten-steps) | `grpo_loop.py train` | 3.6 to 4.4 hours |
| [4. Test the adapters](#4-test-the-adapters) | `grpo_loop.py eval`, twice | 29 to 50 minutes each |
| [5. Check whether the run learned](#5-check-whether-the-run-learned) | none | |
| [6. Stop the app](#6-stop-the-app) | `modal app stop` | |

## What you need

| Need | How |
| --- | --- |
| The modal CLI | it comes with `make install` |
| A Modal account, with the CLI authenticated | `uv run --no-sync modal token new` |
| The secrets `huggingface-glossogen` and `vllm-api-key` | [Self-hosted models](local-inference-vllm-mlx.md#one-time-setup) |
| `SELF_HOSTED_API_KEY` in `.env`, equal to the secret's `VLLM_API_KEY` | [Self-hosted models](local-inference-vllm-mlx.md#wire-glossogen-to-it) |
| GPUs on Modal: a B200 or an H200 for the trainer, an H200 or an H100 for the policy server | your workspace's GPU access |

signal_game has no LLM judge, so the games need no provider key other than the self-hosted one.

## Run it

Run every command from the repository root, in one terminal.

### 1. Deploy the app

```bash
unset VIRTUAL_ENV
export GRPO_APP_NAME=grpo-$USER
uv run --no-sync modal deploy modal/grpo/grpo_app.py
```

The app holds the policy server, which plays the games, and the trainer, which updates the model.
`GRPO_APP_NAME` names the app and its volume, so it has to be a name that nobody in your Modal
workspace uses. `uv run --no-sync modal app list` shows the names in use. `unset VIRTUAL_ENV` stops
`uv` from using a virtualenv that your shell has active.

### 2. Create the run

```bash
uv run --no-sync python modal/grpo/grpo_loop.py init --app $GRPO_APP_NAME --run first-item
```

A run is one training job, and `--run` names it. `init` saves adapter 0 on the app's volume. An
adapter is a small set of weights added to the model, and training changes only the adapter.
Adapter k is the adapter after k training steps. Adapter 0 leaves the model's outputs unchanged.

### 3. Train for ten steps

```bash
uv run --no-sync python modal/grpo/grpo_loop.py train \
  --app $GRPO_APP_NAME --run first-item \
  --runs-dir runs --records-dir ~/grpo-records \
  --game-config modal/grpo/signal_game_shapes.json --concurrency 12 \
  --reward first_item --first-step 0 --last-step 9 \
  --seeds-per-step 4 --games-per-seed 6
```

| Flags | What they set |
| --- | --- |
| `--app`, `--run` | the app of step 1 and the run of step 2 |
| `--runs-dir`, `--records-dir` | where GlossoGen writes each game's event log, and where the loop writes its [records](#records) |
| `--game-config`, `--concurrency` | the signal_game config, and how many games play at once |
| `--reward` | `first_item` or `win`, from [Rewards](#rewards) |
| `--first-step`, `--last-step` | the steps to run |
| `--seeds-per-step`, `--games-per-seed` | each step plays 6 games on each of 4 seeds, 24 games in all |

The loop, `grpo_loop.py`, runs on your machine, so keep the machine awake until `train` ends. In
our runs, each of steps 0 to 9 took 13 to 41 minutes. The first step also waits for the policy
server to start. Each step
prints two lines. These come from step 9 of the run `first-item-rep1`:

```
loaded first-item-rep1-step9
step 9: 24/24 games finished, won 36/240 rounds, first item 101/480 player-rounds, 2301 answers (230769 tokens), kl 0.00769, grad norm 0.0150, play 1037s, train 371s
```

A player-round is one player in one round. `first item` counts the player-rounds in which the player
ended on its first item, the alphabetically first item on its own grid. The 230,769 tokens are the
answer tokens that the trainer used. `kl` is the mean [KL term](#the-loss), and it is 0 at step 0.

### 4. Test the adapters

```bash
for step in 10 0; do
  uv run --no-sync python modal/grpo/grpo_loop.py eval \
    --app $GRPO_APP_NAME --run first-item \
    --runs-dir runs --records-dir ~/grpo-records \
    --game-config modal/grpo/signal_game_shapes.json --concurrency 12 \
    --step $step --games-per-seed 6 --seeds $(seq 45 56)
done
```

`--step 10` tests adapter 10, the adapter after step 9. `--step 0` tests the base model. Each test
plays 6 games on each of seeds 45 to 56, which no training step plays. Each test ends with one line.
These come from `first-item-rep1`:

```
eval step 10: 72/72 games finished, won 82/720 rounds, first item 322/1440 player-rounds
eval step 0: 72/72 games finished, won 84/720 rounds, first item 256/1440 player-rounds
```

### 5. Check whether the run learned

Subtract the base model's `first item` count from adapter 10's. For `first-item-rep1`, that is
322 − 256 = +66. Count a run as learned when the difference is above 40. Two tests of the same
model give different counts, and 40 is about twice the standard deviation of the difference of two
such counts (see [How much counts vary](#how-much-counts-vary)). The 40 assumes independent
player-rounds, so it can be too low.

If your run did not learn, train it for 20 more steps and test adapter 30:

```bash
uv run --no-sync python modal/grpo/grpo_loop.py train \
  --app $GRPO_APP_NAME --run first-item \
  --runs-dir runs --records-dir ~/grpo-records \
  --game-config modal/grpo/signal_game_shapes.json --concurrency 12 \
  --reward first_item --first-step 10 --last-step 29 \
  --seeds-per-step 4 --games-per-seed 6
```

Then run the `eval` command of section 4 once, with `--step 30`, and compare its count with the
base model's count from section 4, by the same rule. Do not test `--step 0` again: the loop refuses
to play a game whose log it already holds. `first-item-rep3` trained to step 29 in two `train`
calls, and its steps 10 to 29 took 9.5 hours, 21 to 48 minutes each. Its adapter 30 ended on the
first item in 632 of 1,440 player-rounds, against 257 for the base model (see
[Training longer](#training-longer)).

### 6. Stop the app

```bash
uv run --no-sync modal app stop $GRPO_APP_NAME --yes
```

The policy server keeps a GPU running until you stop the app, even when no game is playing.
Stopping the app keeps the volume, which holds the adapters.
`uv run --no-sync modal volume delete $GRPO_APP_NAME` removes it, and
`uv run --no-sync modal dict delete $GRPO_APP_NAME-adapters` removes the app's Dict.

## How it works

| Part | Where it runs | What it does |
| --- | --- | --- |
| The loop, `grpo_loop.py` | your machine | plays the games with `glossogen run`, computes the rewards, and sends each batch to the trainer |
| The policy server | the app, on an H200 or an H100 | a vLLM server that serves the model with one adapter, under the name `<run>-step<k>` |
| The trainer | the app, on a B200 or an H200 | updates the adapter and saves it on the volume |
| The volume | Modal, named `$GRPO_APP_NAME` | each run's adapters and settings |
| The Dict | Modal, named `$GRPO_APP_NAME-adapters` | a small key-value store on Modal. The loop writes into it the adapter that the policy server has to load |

The model weights come from the shared `huggingface-cache` volume, as for the
[serving apps](../modal/README.md). The first start downloads them if they are not there. The
trainer stops 20 minutes after its last call. When a step's games take longer than 20
minutes, the next step starts a new trainer, which loads the adapter from the volume.

### One training step

In step k:

1. The policy server loads adapter k. The loop waits until the server reports it as loaded.
2. The loop plays 6 games on each of the step's 4 seeds, seeds 1000 + 4k to 1003 + 4k. The model
   plays both seats of every game at temperature 1.0, so the 6 games of a seed differ. Every game
   runs with `record_token_ids=true`, so its event log holds the token ids of every prompt and
   answer.
3. The reward gives each player a score of 0 or 1 in each round. A player's advantage in a round
   is its score minus the mean score of its seat in that round, over the seed's finished games.
4. The loop builds each player's prompts and answers from the logged token ids. It marks every
   answer token with the advantage of its round. An answer's round is the round of its first tool
   call. An answer without a tool call takes the round of the player's previous tool call, and
   an answer before the player's first tool call gets advantage 0.
5. The trainer takes one gradient step on these sequences and saves adapter k+1.

A game that ends without `simulation_ended` is left out of the batch. When a seed has fewer than 2
finished games, its answer tokens get advantage 0.

### The loss

The method is GRPO (group relative policy optimization), and a group is the finished games of one
seed. Some versions of GRPO divide the advantage by the group's standard deviation, and this loop
does not. The loss of each answer token is `-advantage × log p_policy(token) + 0.02 × k3`, averaged
over the batch's answer tokens. The policy is the model with its current adapter.

k3 estimates the KL divergence between the policy and the base model on that token. The KL
divergence measures how far one model's token probabilities are from another's. With
r = log p_base − log p_policy, k3 = exp(r) − r − 1, capped at 10. k3 is 0 when the two models give
the token the same probability. The `kl` that each step prints is the mean k3 over the batch's
answer tokens.

A seat's advantage in a round is 0 when the seat scored the same in that round in every finished
game of the seed. Only k3 then acts on that seat's answer tokens from that round.

### Rewards

[signal_game_rewards.py](../modal/grpo/signal_game_rewards.py) defines the rewards that `--reward`
accepts:

| `--reward` | A player scores 1 in a round when |
| --- | --- |
| `win` | the round was won: both players ended on the same item |
| `first_item` | the player ended on the alphabetically first item of its own grid |

A player can score on `first_item` whatever its partner does. Each item is a colour and a shape,
such as `blue star`. The game config uses the colours red, blue and green, and the shapes circle,
triangle and star. In alphabetical order, blue comes before green and red, and circle before star
and triangle. So a grid's first item is a blue item whenever the grid holds one, and the blue circle
when the grid holds a blue circle. A blue item of another shape on the same grid does not score.

### Settings

| Setting | Where |
| --- | --- |
| LoRA rank 32 and alpha 64, learning rate 1e-4, k3 weight 0.02, gradient norm clipped at 1.0 | `SETTINGS` in `grpo_app.py`. The trainer uses the deployed settings. `init` also saves them as `runs/<run>/settings.json` on the volume |
| Seeds per step, games per seed, games at a time | the `train` and `eval` flags |
| Grid, items, rounds, temperature | the game config, `signal_game_shapes.json` |

### Records

Each game's event log lands in `--runs-dir`, under `signal_game/`. A training game's labels are
`grpo`, `reward=<reward>`, `run=<run>`, `step=<k>`, `seed=<seed>` and `game=<n>`. A test game
has the same labels without `reward=`, and with `grpo_eval` in place of `grpo`. The loop's own
records are in `<records dir>/<run>/`:

| Path | What it holds |
| --- | --- |
| `steps.jsonl` | one line per training step: the printed counts, the rounds won in each game, and the trainer's metrics |
| `eval.jsonl` | one line per test: the rounds won and the first-item count of each game, grouped by seed, and the totals |
| `configs/` | each seed's game config |
| `game_logs/` | the terminal output of each `glossogen run`, named `<label>_step<k>_seed<seed>_game<n>.log` |

### Resuming after a stop

The adapters are on the volume, at `runs/<run>/adapters/step_<k>/`. To resume, find the highest k
for which that folder exists, and run `train` with `--first-step k`. The trainer loads adapter k
from the volume. The loop refuses to play a game whose log is already in `game_logs/`. To run a
step again after it stopped partway, first move that step's logs out of `game_logs/`.
`steps.jsonl` then gets a second line for that step.

### Another scenario

To train on another scenario, write a module like `signal_game_rewards.py`. It reads a game's
events and gives each agent a score in each round. `grpo_loop.py` imports `Reward`,
`PlayerRound`, `GameOutcome`, `game_outcome` and `player_score` from that module. It reads the
`GameOutcome` fields `finished`, `players`, `rounds`, `won_rounds`, `first_item_finishes`, `moves`
and `player_rounds_without_move`. Your module has to provide all of them, or `grpo_loop.py` has
to change. Set `SCENARIO` in `grpo_loop.py` to the scenario's name, and pass its config as
`--game-config`. The policy has to play every agent of the game, because the policy server
serves one adapter under one name.

## Our runs

The commands above ran four times from 23 to 25 Nov 2026, as the runs `tutorial-check`,
`first-item-rep1`, `first-item-rep2` and `first-item-rep3`. `tutorial-check` ran step 0 on an
earlier revision of `grpo_loop.py` and resumed at step 1 the next day. Two of the four learned
within ten steps:

| Run | Base model | Adapter 10 | Difference |
| --- | --- | --- | --- |
| `first-item-rep1` | 256 | 322 | +66 |
| `first-item-rep2` | 266 | 309 | +43 |
| `first-item-rep3` | 257 | 246 | −11 |
| `tutorial-check` | 234 | 221 | −13 |

Each count is the player-rounds, of 1,440, that ended on the first item in one test on seeds 45 to
56. The base model's column is each run's own test of adapter 0. Players who each ended on a
random square would end on the first item in 241, so the base model ends there about as often as
random play.

Runs of the same commands differ because no random seed is fixed for them. The policy samples every
answer at temperature 1.0. The trainer draws the adapter's A matrices at random and sets its B
matrices to 0. So adapter 0 leaves the model's outputs unchanged, and the later adapters depend on
the A matrices.

### How much counts vary

Two tests of the same model on the same seeds give different counts. The binomial standard
deviation treats each player-round as an independent draw. For a count near 250 of 1,440, it is
about 14, and the difference of two such counts has a standard deviation of about 20. The
player-rounds of one game share its grids and its history, so the binomial value can understate
the spread.

The base model played seeds 1000 to 1003 five times: at step 0 of each of the four runs, and in
one test of adapter 0. Those five counts, each out of 480 player-rounds, have a standard deviation
of 8.5, and the binomial value is 8.1. Five counts give only a rough estimate.

### Training longer

`first-item-rep3` ran `train` with `--last-step 19`, and then with `--first-step 20 --last-step 29`.
On seeds 45 to 56, its players ended on the first item in 257 of 1,440 player-rounds with adapter
0, 246 with adapter 10, 346 with adapter 20 and 632 with adapter 30. This is one run, so it does
not show how often a run learns within 30 steps.

With adapter 30, the players won 131 of 720 rounds, and with adapter 0, 88. Both players ended on a
blue circle in 74 of those 131 rounds, and in 10 of the 88. When both grids hold a blue circle,
two players who each end on their first item end on the same item and win the round.

### During training

The per-step counts of a run are `first_item` in its `steps.jsonl`. Step k plays its own seeds, so
compare each step with the base model on the same seeds. The base model's column comes from one
test of adapter 0 on seeds 1000 to 1039, which took 1.7 hours. A step's count is the sum over its
four seeds. Our record of that test predates `first_item_by_seed`, so we counted its games from
their event logs. A record written by the current loop holds each game's count in
`first_item_by_seed`.

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

Each count is out of 480 player-rounds. Step 0 of every run plays adapter 0, so the five counts of
step 0 all come from the base model. They range from 68 to 89. Over steps 5 to 9, the base model
has 445, and the runs have 536, 523, 422 and 419. To check a run before testing it, compare its sum
over steps 5 to 9 with 445. About 54 is twice the standard deviation of the difference of two such
sums.

### Random-square and start-square baselines

[first_item_baselines.py](../modal/grpo/first_item_baselines.py) prints two counts of
player-rounds that end on the first item, one line per step. The first is the expected count if
each player ended on a random square. The second is the count if each player stayed on its start
square. Over steps 5 to 9 they are 396 and 432, and on seeds 45 to 56 they are 241 and 216.

```bash
uv run --no-sync python modal/grpo/first_item_baselines.py \
  --game-config modal/grpo/signal_game_shapes.json --games-per-seed 6 \
  --last-step 9 --seeds-per-step 4 --held-out-seeds $(seq 45 56)
```

### Runs with the `win` reward

Before the four runs above, two runs trained with the `win` reward, for 10 and 12 steps, at
learning rates 1e-4 and 2e-5. Neither won more rounds than the base model. On seeds 42 to 44, the
10-step run won 20 of 180 rounds, the 12-step run won 19, and the base model won 22. Both trained
on prompts rebuilt from the log's text, so they do not show whether `win` can train the model on
logged token ids.

## Checks and problems

**Train on the logged token ids, never on prompts rebuilt from the log's text.** The loop refuses
a game config without `record_token_ids`. On 20 Nov 2026, 240 of the 2,223 prompts of one step,
rebuilt from the event log's text, differed from vLLM's prompts. One cause is a refused move. The
model received the refusal's error as JSON, and the log holds it as plain text.

**Before you train on a new reward, check that answer tokens get a nonzero advantage.** In step 0's
line of `steps.jsonl`, divide `trainer.advantaged_tokens` by `trainer.marked_tokens`. A share near 0
means that the reward gives nearly every player of a seed the same score, so the adapter changes
only through k3. At step 0, the share was 41% and 47% in the two runs under [Our runs](#our-runs)
that learned, and 57% and 65% in the two that did not. Four runs are too few to tell whether the
share predicts learning.

**Keep the policy server on an H200 or an H100.** On 18 Nov 2026, with LoRA on, vLLM 0.31 failed
twice while capturing CUDA graphs: once on a B200, and once on a GPU whose type was not recorded.
The app's `serve` function asks for an H200 or an H100.

**Check the volume before you run `init` again.** `init` refuses a run that already exists on the
volume. An `init` call can create the run even when your terminal shows an error. If `uv run
--no-sync modal volume ls $GRPO_APP_NAME runs/<run>/adapters` lists `step_0`, go on with `train`.

**If `train` ends before `--last-step`, read its line that starts with `stopping:`.** The loop
stops after a step whose `kl` is above 0.3. It also stops after a step in which fewer than 75% of
the started games finished. A game that failed before `glossogen run` printed its run id
does not count as started.

**Expect a few retried requests.** Modal answers HTTP 303 to a request that has run for 150
seconds. GlossoGen then sends the request again, up to 3 attempts, and then restarts the agent's
turn. In step 0 of `tutorial-check`, 8 of 2,156 requests got a 303, and every game finished. An
answer that takes more than 150 seconds to generate never reaches the batch.

## Where to go next

- [Running simulations](running-simulations.md#self-hosted-and-local-models) explains
  `record_token_ids` and the self-hosted provider.
- [Reading runs from code](reading-runs-from-code.md) covers the event log, which
  `signal_game_rewards.py` reads.
- [modal/grpo/README.md](../modal/grpo/README.md) lists the files and how to run their tests.
