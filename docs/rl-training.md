# Training a model with RL

These steps train Qwen3.8-27B by reinforcement learning (RL) on signal_game, with
[platoon](https://github.com/ApGa/platoon) 0.6.0 and the code in
[modal/platoon/](../modal/platoon/README.md). In signal_game, two players each have their own grid
of squares, and each square holds an item, such as `blue star`. Each player starts a round on a
square of its own grid and can move to other squares of that grid. A game has two seats, player_a
and player_b, one per player.

Platoon plays the games on your machine, scores them and computes each answer's advantage. It
sends each batch of answers to a training service that implements the Tinker API, the API of
Thinking Machines' hosted training service. This repository's service,
[tinker_service](../modal/platoon/tinker_service/__init__.py), runs on Modal. It trains a LoRA
adapter and serves each new adapter with vLLM.

The service has run only on a CPU, in the tests, with stand-ins for the model.
[Before the first GPU run](#before-the-first-gpu-run) lists what has not been checked on a GPU.

| Step | Command |
| --- | --- |
| [1. Install the environments](#1-install-the-environments) | `make install`, then `uv sync` in `modal/platoon` |
| [2. Deploy the service](#2-deploy-the-service) | `modal deploy platoon_app.py` |
| [3. Train](#3-train) | `platoon train configs/signal_game.yaml` |
| [4. Read the evaluations](#4-read-the-evaluations) | `python -m glossogen_platoon.eval_report` |
| [5. Stop the app](#5-stop-the-app) | `modal app stop` |

## What you need

| Need | How |
| --- | --- |
| The repository's environment, in which the games run | `make install` |
| The platoon project's environment, in which `platoon train` runs | `uv sync` in `modal/platoon` |
| A Modal account, with the CLI authenticated | `uv run --no-sync modal token new` |
| The Modal secrets `huggingface-glossogen` and `vllm-api-key` | [Self-hosted models](local-inference-vllm-mlx.md#one-time-setup) |
| The Modal secret `platoon-tinker-api-key`, holding `TINKER_API_KEY` | a key that you choose, starting with `tml-`, which the Tinker SDK requires |
| Two H200 GPUs in one Modal container | your workspace's GPU access |

signal_game has no LLM judge, so the games need no provider key.

## Run it

### 1. Install the environments

```bash
make install
cd modal/platoon
VIRTUAL_ENV= uv sync
```

The platoon project has an environment of its own, in `modal/platoon/.venv`. Platoon pins
tinker-cookbook below 0.4. That tinker-cookbook needs a transformers release that needs
huggingface-hub below 2, and GlossoGen needs huggingface-hub 2.4 or later. Run every command below
from `modal/platoon`. `VIRTUAL_ENV=` stops `uv` from using a virtualenv that your shell has active.

### 2. Deploy the service

```bash
export PLATOON_APP_NAME=platoon-$USER
VIRTUAL_ENV= uv run --no-sync --project ../.. modal deploy platoon_app.py
```

`--project ../..` runs the modal CLI from the repository's environment. `PLATOON_APP_NAME` names
the app and its volume, so it has to be a name that nobody in your Modal workspace uses. The deploy
prints the URL of the app's `tinker_api` function. The service answers there once vLLM and the
trainer have loaded the model. The first start downloads the model's weights into the shared
`huggingface-cache` volume, unless they are already there.

### 3. Train

```bash
export TINKER_BASE_URL=<the URL that the deploy printed>
export TINKER_API_KEY=<the key in the platoon-tinker-api-key secret>
VIRTUAL_ENV= uv run --no-sync platoon train configs/signal_game.yaml
```

`platoon train` runs on your machine, and so do the games, so keep the machine awake until it
ends. The config trains for 10 steps. Each step plays 6 games on each of 4 seeds, 24 games in all,
with at most 12 games playing at once. Each argument after the config sets one value of it, for
example:

| Argument | What it sets |
| --- | --- |
| `train.max_training_steps=30` | the number of training steps |
| `stats.trial_name=first-item-rep2` | the run's name, and so its folder |
| `train.workflow_config.rollout_config.extra.glossogen_reward=win` | the reward, `first_item` or `win`, from [Rewards](#rewards) |

The run writes to `../../runs/platoon/signal-game/<trial name>/`: its config, its checkpoints in
`checkpoints.jsonl`, and the rollouts of each evaluation under `rollouts/eval/<step>/`. The games
are ordinary GlossoGen runs in the repository's `runs/signal_game/`. A training game has the
labels `platoon`, `seed=<seed>` and `task=seed-<seed>`, and an evaluation game has `platoon_eval`
in place of `platoon`.

The console log prints every metric of every step. Check these metrics on each step:

| Metric | What it is |
| --- | --- |
| `batch/task_reward/avg` | the mean score per player-round of the step's games under the trained reward |
| `credit/glossogen/kl_k3` | the mean KL estimate between the sampling policy and the base model, per answer token ([The KL term](#the-kl-term)) |
| `optim/grad_norm` | the gradient norm before clipping |
| `batch/stale_groups` | the groups that the step dropped because their games are too old ([Games that run ahead of training](#games-that-run-ahead-of-training)) |
| `optim/kl_sample_train_v1` | the KL estimate between the policy that sampled the answers and the policy that trains on them |

A player-round is one player in one round. A group is the 6 games of one seed in one step. Set `stats.wandb.mode=online` to log the metrics to
Weights & Biases as well. That needs `WANDB_API_KEY`.

### 4. Read the evaluations

The config evaluates the policy at step 0, before the first update, and at steps 5 and 10. Each
evaluation plays 6 games on each of seeds 45 to 56. No training step plays those seeds. Each
evaluation holds 72 games, 720 rounds and 1,440 player-rounds.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen_platoon.eval_report \
  --run ../../runs/platoon/signal-game/first-item
```

It prints one line per evaluation, in this form:

```
eval step 0: 72 games finished, won <n>/720 rounds, first item <n>/1440 player-rounds
```

`first item` counts the player-rounds in which the player ended on its first item, the
alphabetically first item on its own grid. To check whether a run learned, subtract the count of
step 0 from the count of step 10. Count a run as learned when the difference is above 40.

Two evaluations of the same policy give different counts. The binomial standard deviation treats
each player-round as an independent draw. For a count near 250 of 1,440, it is about 14, and the
difference of two such counts has a standard deviation of about 20. So 40 is about twice that
standard deviation. The player-rounds of one game share its grids and its history, so the binomial
value can understate the spread, and 40 can be too low.

Two counts that need no model give a scale for these numbers. If each player ended on a random
square, the expected count on seeds 45 to 56 would be 241 of 1,440. If each player stayed on its
start square, the count would be 216. This command prints both:

```bash
VIRTUAL_ENV= uv run --no-sync --project ../.. python -m glossogen_side.first_item_baselines \
  --game-config configs/signal_game_shapes.json --games-per-seed 6 --seeds $(seq 45 56)
```

### 5. Stop the app

```bash
VIRTUAL_ENV= uv run --no-sync --project ../.. modal app stop $PLATOON_APP_NAME --yes
```

The app keeps two H200 GPUs running until you stop it, even when no game is playing. Stopping the
app keeps the volume, which holds the checkpoints. To resume a run, deploy the app again and run
the same `platoon train` command. Platoon starts from the newest checkpoint of the run, on the volume.

## Other setups

| Setup | How |
| --- | --- |
| player_b plays the base model and does not train | `configs/frozen_partner.yaml` |
| player_b plays a model outside platoon, which platoon neither records nor trains | `environments.0.harness_options.external_seats='{player_b: {model: <model>, provider: <provider>, base_url: <url or null>}}'` on the command line |
| Each seat trains an adapter of its own | `configs/seat_policies.yaml` |

In `frozen_partner.yaml`, the role `player_b` samples the policy `partner`, a frozen copy of the
base model on the same service. In `seat_policies.yaml`, the role `player_b` samples the policy
`seat_b`, which trains its own adapter beside the adapter of player_a. Both use platoon's
`policies:` and `agents:` settings, which platoon marks experimental. Platoon's
[RFC 0003](https://github.com/ApGa/platoon/blob/v0.6.0/docs/rfcs/0003-multi-policy-training.md)
lists a GPU run that checks that two policies both learn as milestone M3. Platoon 0.6.0 implements
milestones M1, M2 and M4 of that RFC.

A seat in `external_seats` plays any model that GlossoGen can run, through GlossoGen's
`model_overrides`. A `self-hosted` one needs a `base_url` and `SELF_HOSTED_API_KEY` in your
environment. Another provider needs its own key.

## How it works

| Part | Where it runs | What it does |
| --- | --- | --- |
| `platoon train` | your machine, in the platoon project's environment | draws the seeds, runs the episodes, credits them, and sends each batch to the service |
| The harness, `glossogen_platoon/harness.py` | your machine, in `platoon train` | plays one game per episode with `glossogen run` |
| The scorer, `glossogen_side/score_game.py` | your machine, in the repository's environment | reads a finished game's event log and scores each seat in each round |
| The episode program and the credit estimator | your machine, in `platoon train` | turn the scores into each answer token's advantage |
| The service, `tinker_service` | Modal, on two H200 GPUs | trains the LoRA adapters with PEFT on one GPU, and samples with vLLM on the other |
| The volume | Modal, named `$PLATOON_APP_NAME` | the checkpoints, under `checkpoints/<model id>/` |

### One episode

An episode is one game on one seed. Platoon's model gateway is an OpenAI-compatible server that
platoon runs on your machine. It renders each request into tokens, samples the policy through the
service, and records every call. An agent is one caller of the gateway, with a URL of its own. The
gateway records each agent's calls in order, as the agent's trajectory, and platoon trains on the
tokens that the trajectory holds. A policy is a model that agents sample: `main`, the adapter that
the run trains, or another policy that the config declares.

1. Platoon starts the harness as the episode's root agent. The root agent makes no model call.
2. For each seat, the harness asks the gateway for a new agent whose role is the seat's name
   (`POST /v1/platoon/agents`). Each agent samples the policy that `agents.roles` binds to its
   role, and `main` when the config binds none.
3. The harness runs `glossogen run signal_game` in the repository's environment.
   `SELF_HOSTED_BASE_URLS` maps each seat's model name to its agent's URL, so each seat's requests
   reach its own agent.
4. When the game ends, the scorer writes the game's labels and prints each seat's score in each
   round, and the round of each of its model answers.
5. The episode program gives each seat's trajectory one span per round. A span holds the seat's
   model calls of that round, and its reward is the seat's score in that round. A call belongs to
   the round of its answer's first tool call. A call without a tool call belongs to the round of
   the seat's previous tool call. A call before the seat's first tool call belongs to no span.
6. The episode's reward is the mean score per player-round under the trained reward.

The program matches each `llm_response_received` of a seat in the event log to a call that the
gateway recorded for that seat. It compares the names of the answer's tool calls and the first 40
characters of its text, and takes the next recorded call that has both the same. The gateway
records some calls that the event log holds no response for: pydantic-ai asks the model again after
an empty answer or a call to a tool that does not exist. Such a call belongs to no span. A response
in the event log that matches no recorded call fails the episode, which then trains nothing.

### Rewards

The rewards are in [signal_game_rewards.py](../modal/platoon/glossogen_side/signal_game_rewards.py):

| Reward | A player scores 1 in a round when |
| --- | --- |
| `win` | the round was won: both players ended on the same item |
| `first_item` | the player ended on the alphabetically first item of its own grid |

A player scores on `first_item` regardless of what its partner does. Each item is a colour and a
shape. The game config uses the colours red, blue and green, and the shapes circle, triangle and
star. So the first item of a grid that holds a blue circle is the blue circle.

### Credit

For each group, the credit estimator `glossogen-round-baseline` gives each answer token an
advantage:

- A call in a span gets the span's reward minus the seat's baseline in that round. The baseline
  is the mean span reward of the same seat in the same round, over the group's games.
- A call in no span gets 0 from the rounds. The KL penalty below still applies to its tokens.

A seat's advantage in a round is 0 when the seat scored the same in that round in every game of
the group.

### The KL term

The config names a frozen policy, `base`, which is the base model on the same service. For every
group, the base model scores each token that the policy sampled. Each answer token's advantage then
gets `-0.02 × (sampled logprob − base logprob)`. That difference estimates the KL divergence of the
sampling policy from the base model, so the penalty pulls the policy toward the base model.

The estimator also computes k3 = exp(r) − r − 1 per answer token, with r = base logprob − sampled
logprob, and logs the group's mean as `credit/glossogen/kl_k3`. When a group's mean k3 is above
0.3, the estimator raises `KlLimitExceeded`, and the run stops. The checkpoints that the run saved
before stay on the volume. `credit_options` in the config sets the coefficient (`kl_coef`) and the
limit (`max_kl`).

### Games that run ahead of training

Each training step publishes a new adapter to vLLM, which is a new version of the policy. Platoon
starts the games of the next steps while the service trains, so a game can sample an older version
than the one that trains on its answers. `train.max_staleness: 3` lets a group train when its oldest
answer was sampled at most 3 versions before the version that trains on it. A group whose oldest answer is older is dropped, and the step counts it in
`batch/stale_groups`.

The value 3 is an estimate from game and step times measured over 60 training steps of
Qwen3.8-27B on this game config, with 12 games at once, under another trainer on one B200 or H200:

- The slowest of a step's 24 games took about 700 seconds on average. The median of the 1,440
  games took 308 seconds.
- Training a batch took about 500 seconds on average.

At most 12 games play at once, so there are 12 game slots. With `train.permit_release: rollout`,
each slot comes back when its game ends, and the next game starts on it. A group's last game can
wait about one median game for a slot, and then take as long as the slowest game. So a group's games
can span about 308 + 700 ≈ 1,000 seconds. At about 500 seconds per step, the policy moves about
2 versions in that time. The group then waits up to one more step to train: 2 + 1 = 3. The service's step
time on two H200 GPUs has not been measured. When `batch/stale_groups` is above 0, raise
`train.max_staleness`.

### The loss

The loss is platoon's default, CISPO. For each answer token it is
`−stopgrad(clamp(ratio, 0, 5)) × advantage × log p`, where `ratio = exp(log p − sampled logprob)`
and `log p` is the logprob of the token under the policy that trains. The clamp caps the ratio at 5
for answers sampled by an older policy. The service sums the loss over the tokens. Platoon divides
each advantage by the number of answer tokens in the microbatch, which is the whole batch under
this config, so the sum acts as a mean.

| Setting | Value | Where |
| --- | --- | --- |
| LoRA rank and alpha | 32 and 64 | `train.lora_rank`; the service sets alpha to twice the rank |
| Optimizer | AdamW, learning rate 1e-4, betas 0.9 and 0.999, no weight decay | `train.optimizer` |
| Gradient clipping | norm 1.0 | `train.optimizer.grad_clip_norm` |
| KL coefficient and limit | 0.02 and 0.3 | `environments.0.credit_options` |
| Seeds per step, games per seed, games at once | 4, 6 and 12 | `train.batch_size`, `train.workflow_config.group_size`, `train.max_concurrent_rollouts` |
| Grid, items, rounds, temperature | | the game config, `configs/signal_game_shapes.json` |
| Training and evaluation seeds | 1000 to 1119, and 45 to 56 | `configs/signal_game_tasks.jsonl`, written by `python -m glossogen_platoon.task_table` |

### The service

`tinker_service` implements the part of the Tinker API that platoon's training calls:

| Route | What the service does |
| --- | --- |
| `create_session`, `session_heartbeat`, `telemetry` | answers; it stores each session's id and nothing else about it |
| `create_model` | adds a LoRA adapter, with its own AdamW optimizer, for a new model id |
| `forward_backward` | computes the logprob of each answer token and the loss, and adds the loss's gradient to the adapter's |
| `optim_step` | clips the gradient norm, steps the optimizer, and clears the gradient |
| `save_weights`, `load_weights`, `weights_info` | saves, loads and describes a full checkpoint: the adapter and its optimizer state |
| `save_weights_for_sampler` | saves the adapter, loads it into vLLM, and opens a sampling session on it |
| `create_sampling_session`, `asample` | samples from an adapter or from the base model, with vLLM's `/v1/completions` and the prompt's token ids |
| `retrieve_future` | returns the result of a request that took time |
| `DELETE training_runs/.../checkpoints/...` | deletes a recovery checkpoint that platoon no longer needs |

Platoon opens one Tinker training client per trained policy, and the service gives each client an
adapter of its own, so one service trains several policies at once. The service keeps the 6
newest adapters of each policy loaded in vLLM and unloads older ones. Rollouts can sample a
policy up to 3 versions old, so 6 leaves room. The service keeps its adapters, optimizers and
sampling sessions in memory, and a restart of its container loses them. The running `platoon train` then gets errors
from the service. A new `platoon train` resumes from the newest checkpoint on the volume.

### Before the first GPU run

The tests run the service with a unigram model, a scripted sampler, and a tiny random model of
Qwen3.8-27B's architecture. These have not run on a GPU:

- the image, which installs the trainer's packages and vLLM 0.31, with vLLM in a virtualenv of its
  own, and loading Qwen3.8-27B in it;
- vLLM's answers to the service's requests: that the sampled token ids end with `<|im_end|>`, that
  `prompt_logprobs` come back for every prompt token, and that each adapter loads at runtime;
- Qwen3.8-27B's chat template through platoon's gateway with a real model's answers;
- the memory of the trainer on one H200 for the longest games, and the time of a step.

Platoon's model gateway renders each prompt with Qwen3.8-27B's own chat template
(`renderer_name: chat_template`) and parses the model's tool calls from the sampled tokens. The
trainer trains on the same tokens. The tests use platoon's toy tokenizer and its `qwen3_instruct`
renderer instead, so the first GPU run is the first check that the gateway parses Qwen3.8-27B's
real answers.

### Another scenario

To train on another scenario, write a scorer like `glossogen_side/score_game.py` that gives each
agent a score in each round, and a harness like `glossogen_platoon/harness.py` that runs the
scenario with one platoon agent per seat. The episode program and the credit estimator need only each
seat's score in each round and the round of each answer. They have run only on signal_game.

## Token ids in the event log

Platoon takes the tokens that it trains on from its gateway, and does not read GlossoGen's event
log for them. The knob `record_token_ids` writes token ids and logprobs into the event log, for a
trainer that reads the event log instead.

With `record_token_ids=true`, each request of an agent under `--provider
self-hosted` asks the server for `return_token_ids` and `logprobs`. Each
`llm_response_received` event of that agent then holds these fields:

| Field | What it holds |
| --- | --- |
| `token_ids_index` | the response's position among the agent's recorded responses, counted from 0 when the agent's runner starts |
| `token_ids` | the token ids of the model's answer |
| `token_logprobs` | the logprob of each answer token, in the same order |
| `prompt_prefix_tokens` | the length of the prompt's prefix: the tokens at its start that match the agent's previous prompt followed by its previous answer |
| `prompt_tail_ids` | the token ids of the prompt after its prefix |

The server returns `token_ids` and `token_logprobs`, and GlossoGen computes the
other fields. `glossogen.run_storage.recorded_token_ids` rebuilds the full
prompts of one agent, with each answer's ids and logprobs.

GlossoGen treats a request as failed in two cases. In the first, the server
returns token ids but not exactly one logprob for each answer token. In the
second, the server gives an answer token a logprob that is not a finite number,
or that is -9999 or lower. vLLM gives -9999 to a token whose logprob it does not
have. GlossoGen tries the request up to 3 times. If all 3 attempts fail, it logs
`agent_run_cycle_failed` and starts a new turn. The failed turn counts toward
`--max-agent-turns`.

vLLM's default `--logprobs-mode` takes logprobs before temperature and the
sampling filters. A config that sets temperature 1.0, top-p 1.0, top-k -1, min-p
0 and presence penalty 0 turns every filter and the penalty off, and GlossoGen
sends those values with every request of an agent. vLLM fills each sampling
value that a request leaves out from the model's `generation_config.json`.
Qwen3.8-27B's file sets top-k 20 and top-p 0.95, so a request without them
samples with those filters on. With the filters off, the logged logprobs are
those of the distribution that the server sampled from. With another
temperature or filter, they differ from it.

pydantic-ai marks a tool `strict` when the tool's schema allows it. vLLM then
uses a grammar to force the model's tool calls to match the tool schemas. It
computes the logged logprobs after the grammar has removed the tokens it
forbids. A token that the grammar leaves as the only choice is logged with a
logprob near 0, a probability near 1, even when the model without the grammar
gives it a low probability. A trainer that computes its own logprobs finds the
logged logprob higher at those tokens.

## Tests

The tests run on a CPU with scripted players and need no API key:

```bash
cd modal/platoon
VIRTUAL_ENV= uv run --no-sync pytest
```

[modal/platoon/README.md](../modal/platoon/README.md) lists what each test file checks.

## Where to go next

- [Running simulations](running-simulations.md#self-hosted-and-local-models) explains the
  self-hosted provider.
- [Reading runs from code](reading-runs-from-code.md) covers the event log, which the scorer reads.
- Platoon's [documentation](https://github.com/ApGa/platoon/tree/v0.6.0/docs) explains its
  configs, credit estimators and policies.
