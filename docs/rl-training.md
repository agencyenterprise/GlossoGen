# Training a model with RL

You can train Qwen3.8-27B by reinforcement learning (RL) on signal_game with the code in
[modal/grpo/](../modal/grpo/README.md). The model plays both seats of each game. Each player gets
a score of 0 or 1 in each round. A trainer then updates a LoRA adapter, a small set of weights
added to the model. Answers from rounds that scored above their seed's mean become more likely,
and answers from rounds below it become less likely. The commands of the worked example:

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

Run the commands from the repository root. The loop runs on your machine, so keep it awake while
`train` runs. Ten steps took 3.2 hours in the run under [What to expect](#what-to-expect), 15 to 24
minutes per step.

## What you need

| Need | How |
| --- | --- |
| A Modal account, with the CLI authenticated | `modal token new` |
| The secrets `huggingface-glossogen` and `vllm-api-key` | [Self-hosted models](local-inference-vllm-mlx.md#one-time-setup) |
| `SELF_HOSTED_API_KEY` in `.env`, equal to the secret's `VLLM_API_KEY` | [Self-hosted models](local-inference-vllm-mlx.md#wire-glossogen-to-it) |
| GPUs on Modal: a B200 or an H200 for the trainer, an H200 or an H100 for the server | your workspace's GPU access |
| A name for the app that nobody in your Modal workspace uses | `modal app list` |

`GRPO_APP_NAME` is the name of the app and of its volume. The loop asks the server to load an
adapter through a Modal Dict named `<GRPO_APP_NAME>-adapters`. The model weights come from the
shared `huggingface-cache` volume, as for the [serving apps](../modal/README.md). signal_game has
no LLM judge, so the games need no provider key other than the self-hosted one.

## How one training step works

In step k, the loop and the trainer do the following:

1. The policy server, the vLLM server in the app, loads adapter k and serves it as the model
   `<run>-step<k>`. The policy is the model with its current adapter. Adapter 0 leaves the base
   model's outputs unchanged.
2. The loop plays 6 games on each of the step's 4 seeds. With `--seeds-per-step 4`, step k plays
   seeds 1000 + 4k to 1003 + 4k. Both seats of a game play the policy at temperature 1.0, so the
   6 games of a seed differ. Every game runs with `record_token_ids=true`, so its event log holds
   the token ids of every prompt and answer.
3. The reward gives each player a score of 0 or 1 in each round. A player's advantage in a round
   is its score minus the mean score of the same seat (`player_a` or `player_b`) in that round,
   over the seed's finished games.
4. The loop reads each player's prompts and answers from the logged token ids, and marks every
   answer token with its round's advantage. An answer's round is the round of its first tool
   call. An answer without a tool call takes the round of the agent's previous call.
5. The trainer takes one gradient step on these sequences and saves adapter k+1.

### The loss

This method is GRPO (group relative policy optimization), and its group is the set of finished
games of one seed. The loss of each answer token is `-advantage × log p(token) + 0.02 × k3`,
averaged over the batch's answer tokens.

k3 estimates the KL divergence between the adapted model and the base model on that token. With
r = log p_base − log p_adapted, k3 = exp(r) − r − 1, capped at 10. The k3 term grows as the
adapter moves away from the base model. The `kl` that each step prints is the mean k3 over the
batch's answer tokens.

When all of a seed's finished games scored the same in a round, the advantage is 0, and only the
k3 term acts on that round's answer tokens. A game that ends without `simulation_ended` is left
out of the batch. When a seed has fewer than 2 finished games, every answer token of its finished
game gets advantage 0.

## Settings and records

| Setting | Where |
| --- | --- |
| LoRA rank 32 and alpha 64, learning rate 1e-4, k3 weight 0.02, gradient norm clipped at 1.0 | `SETTINGS` in `grpo_app.py`. Redeploy after a change. `init` saves them as `runs/<run>/settings.json` on the volume |
| Seeds per step, games per seed, games at a time | the `train` and `eval` flags |
| Grid, items, rounds, temperature | the game config, `signal_game_shapes.json` |

Each game's event log lands in `--runs-dir`, under `signal_game/`. Its labels are `grpo` for
training or `grpo_eval` for evaluation, with `run=`, `step=`, `seed=` and `game=`. Ten steps and
one evaluation at the sizes above make 258 run directories. The loop's own records are in
`<records dir>/<run>/`:

| Path | What it holds |
| --- | --- |
| `steps.jsonl` | one line per training step |
| `eval.jsonl` | one line per evaluation |
| `configs/` | each seed's game config |
| `game_logs/` | the terminal output of each `glossogen run` |

### Resuming after a stop

The adapters are on the volume, at `runs/<run>/adapters/step_<k>/`. To go on after a stop, run
`train` with `--first-step k`, and the trainer loads adapter k from the volume. The loop refuses
to play a game whose log is already in `game_logs/`. Before you run a step that stopped partway
again, move that step's logs out of `game_logs/`.

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
events and gives each agent a score in each round. Then set `SCENARIO` in `grpo_loop.py` to the
scenario's name, import your module in place of `signal_game_rewards`, and pass the scenario's
config as `--game-config`. `run_step` records the `GameOutcome` fields `won_rounds`,
`first_item_finishes`, `moves` and `player_rounds_without_move`. Your module has to provide
them, or `run_step` and `StepRecord` have to change. Every agent has to play the policy, because
the server serves one adapter under one name.

## What a step prints

On 23 Nov 2026, the `train` command above, with `--run tutorial-check` and `--last-step 0`,
printed:

```
loaded tutorial-check-step0
step 0: 24/24 games finished, won 23/240 rounds, first item 89/480 player-rounds, 2148 answers (191330 tokens), kl 0.00000, grad norm 0.0130, play 1865s, train 567s
```

A player-round is one player in one round. The 191,330 tokens are the answer tokens of the 2,148
answers. The KL is 0 at step 0, because adapter 0 leaves the base model unchanged. Loading adapter
0 and playing the 24 games took 31 minutes, the record's `play_seconds`. Training took 9.5
minutes. The trainer's own step took 8.5 of them, which `steps.jsonl` records as
`trainer.seconds`.

`steps.jsonl` also holds the rounds won in each game of each seed, the moves per player-round,
and the trainer's metrics. `trainer.advantaged_tokens` counts the answer tokens with a nonzero
advantage: 124,189 of 191,330 in this step.

### Retried requests

Modal answers HTTP 303 to a request that has run for 150 seconds. After a 303, GlossoGen sends the
request again, up to 3 attempts, and then restarts the agent's turn. In this step, 8 of the 2,156
requests got a 303, and the other 2,148 got an answer. One agent's turn got a 303 on all 3
attempts, and the runner restarted it. Its game still finished.

## What to expect

The table comes from one ten-step run with the commands above, on 20 Nov 2026. That run recorded
the token ids through a proxy in front of vLLM. It used the same game config, seeds and trainer
settings. The text after the table also draws on earlier runs, which it names.

| Games | Ended on the first item | Random square | Start square |
| --- | --- | --- | --- |
| Step 0, seeds 1000 to 1003, the base model | 83 of 480 | 83 | 84 |
| Steps 8 and 9, seeds 1032 to 1039 | 210 of 960 | 161 | 192 |
| Held-out seeds 42 to 44, adapter 10 | 96 of 360 | 67 | 96 |
| Held-out seeds 42 to 44, the base model | 65 of 360 | 67 | 96 |

### The baselines

The two baseline columns count the player-rounds that would end on the first item. Under random
square, each player ends on a random square of its grid, and the count is the expected one. Under
start square, each player stays on its start square. The seeds' boards set both, so
[first_item_baselines.py](../modal/grpo/first_item_baselines.py) prints them for each step:

```bash
VIRTUAL_ENV= uv run --no-sync python modal/grpo/first_item_baselines.py \
  --game-config modal/grpo/signal_game_shapes.json --games-per-seed 6 \
  --last-step 9 --seeds-per-step 4 --held-out-seeds 42 43 44
```

### During training

At step 0, the base model scored 1 below the start-square baseline. At steps 8 and 9, the policy
scored 18 above it. Across steps 0 to 9, the start-square baseline ranges from 42 to 108 of 480,
so compare each step with its own baselines. Six runs have played step 0 on seeds 1000 to 1003
with the base model, and they scored 79, 83, 84, 85, 89 and 93 of 480.

### On the held-out seeds

Adapter 10 scored 31 more than the base model, and as many as the start-square baseline. The
players did not stop moving. In training, the player-rounds without a move went from 120 of 480
at step 0 to 89 at step 9, and the moves per player-round stayed between 1.6 and 1.9.

Two adapters trained on `win` for 10 and 12 steps scored 85 and 91 on the same held-out seeds.
Each held-out count comes from one evaluation of 18 games. The base model's count comes from the
evaluation of adapter 0 in a `win` run on 18 Nov 2026.

## Before a long run

**Keep `record_token_ids` on in your game config.** The loop refuses a game config without it.
On 20 Nov 2026, the 2,223 prompts of one step were rebuilt from the event log's text, and 0 of
them matched vLLM's prompts token for token.

The log then listed an agent's tools in alphabetical order. From v0.31.19, it lists them in the
order that the model receives them. With the tools put in that order, 240 of the 2,223 prompts
still differed. In one of the differences, the model received a refused move's error as JSON,
and the log holds it as plain text.

**Before you train on a new reward, check how many answer tokens get an advantage.** Step 0's
line in `steps.jsonl` holds `trainer.advantaged_tokens` and `trainer.marked_tokens`. At step 0 on
these seeds, 45% and 51% of the answer tokens had an advantage under `win`, in two runs. Under
`first_item`, 58% to 65% had one, in four runs.

The two `win` runs won 20 and 19 of 180 held-out rounds after 10 and 12 steps, and the base model
won 22. Both trained on prompts rebuilt from the log's text, and one of them used learning rate
2e-5.

**Keep the server on an H200 or an H100.** On 18 Nov 2026, with LoRA on, vLLM 0.31 failed twice
while capturing CUDA graphs: once on a B200, and once on a GPU whose type was not recorded. The
app's `serve` function asks for an H200 or an H100.

**Stop the app when you finish.** The server keeps one GPU running until `modal app stop`, even
when no game is playing. The trainer stops 20 minutes after its last call, and starts again for
the next step.

**Check the volume before you run `init` again.** `init` refuses a run that already exists on the
volume. An `init` call can create the run even when your terminal shows an error. If
`modal volume ls $GRPO_APP_NAME runs/<run>/adapters` lists `step_0`, go on with `train`.

**The loop stops on its own when a step goes wrong.** It stops after a step whose KL is above 0.3,
or in which fewer than 75% of the games that started finished. A game that fails before
`glossogen run` prints its run id counts in neither number.

## Where to go next

- [Running simulations](running-simulations.md#self-hosted-and-local-models) explains
  `record_token_ids` and the self-hosted provider.
- [Reading runs from code](reading-runs-from-code.md) covers the event log, which
  `signal_game_rewards.py` reads.
- [modal/grpo/README.md](../modal/grpo/README.md) lists the files and how to run their tests.
