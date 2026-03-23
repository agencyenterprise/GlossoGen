# Persuasion Debate

Two agents debate trivia questions to study how LLMs handle persuasion. Based on the Persuasion-Balanced Training (PBT) paper by Stengel-Eskin et al. (2025).

## Modes

### Misinformation (Section 4.1)
An adversary agent tries to convince a target agent to abandon a correct answer. The adversary uses a configurable persuasion strategy (logical, emotional, or credibility-based). Measures resistance to negative persuasion.

### Balanced (Section 4.2)
Half of the questions test resistance to negative persuasion (target starts correct, adversary pushes wrong). The other half test acceptance of positive persuasion (target starts wrong, partner pushes correct). Roles alternate every other question.

### Debate (Section 4.3)
Both agents answer genuinely with no adversarial role and no seeded answers. Use model_overrides in knobs to pair models of different strengths. Measures team accuracy, order dependence, and whether the stronger model pulls the weaker one up.

### Seeded Debate (Act 1 replication)
Open-ended debate with seeded answers. Agent A receives the correct answer, Agent B receives a wrong answer. Both agents use the standard open-ended prompt with no persuasion strategy instructions — they discuss naturally. Tests the ordering/anchoring effect: when the weaker model speaks first, it drags the stronger model's accuracy down.

## Two-Phase Turn Structure

Each question (round) has two phases, matching the paper's methodology:

### 1. Blind Phase (independent answers)
Both agents answer the question independently via `submit_initial_answer` without seeing each other's responses. This prevents anchoring bias where the second agent simply adopts the first agent's answer.

### 2. Discussion Phase
Both agents see each other's initial answers and discuss on the shared debate channel. Agents alternate for `max_turns_per_round` turns.

## Agents

- **Agent A** — In misinformation mode, always the target (receives the correct answer). Speaking order is controlled by `agent_order`.
- **Agent B** — In misinformation mode, always the adversary (argues for the wrong answer). Speaking order is controlled by `agent_order`.

## Channels

- **debate** — Single shared channel for discussion (used only during the discussion phase).

## Tools

- `submit_initial_answer(answer)` — Submit an independent answer during the blind phase
- `send_message` — Send a message to the debate channel (discussion phase)

- `submit_final_answer(answer)` — Submit a final answer after discussion

## Round Injections

### Blind Phase Injection
Each agent receives the question text. Injection content varies by mode:
- **Target**: receives the question and a seeded initial answer to believe (correct or wrong depending on mode)
- **Adversary**: receives the question and the answer they are confident about
- **Debater**: receives only the question (no seeded answer, answers from knowledge)

### Discussion Phase Injection
Both agents receive both initial answers and are told to discuss on the debate channel.

## Knobs

| Knob | Values | Description |
|------|--------|-------------|
| mode | misinformation, balanced, debate, seeded_debate | Evaluation mode |
| agent_order | a_first, b_first | Which agent answers first in each phase |
| round_count | int | Number of questions (rounds) |
| max_turns_per_round | int | Maximum discussion turns per question |
| persuasion_strategy | logical, emotional, credible, null | Adversary's approach (required for misinformation/balanced, null for debate/seeded_debate) |
| model_overrides | dict | Per-agent model overrides for pairing different strengths |

## Question Bank

A `questions.json` file with 100 TriviaQA questions is checked in. To refresh or customize the question set, run the download script:

```bash
pip install datasets
python src/schmidt/scenarios/persuasion_debate/download_triviaqa.py --count 100
```

This streams questions from the TriviaQA validation split (unfiltered config) and writes them to `questions.json` in this directory. The `--count` flag controls how many questions to include. The `--output` flag overrides the output path.

The `datasets` library is only needed for this script — it is not a runtime dependency of the scenario.

## Act 1 — Exact Replication

Tests the ordering/anchoring effect from the paper. A strong model (Opus) gets the correct answer, a weak model (Haiku) gets a wrong but plausible answer. Both agents use the standard open-ended prompt — no persuasion strategy instructions, no "convince them" directives. Two knobs presets test whether speaking order affects the outcome.

Both agents first answer independently (blind phase), then discuss naturally for 4 turns. The blind phase isolates each agent's initial belief before exposure to the other's answer.

### Generating wrong answers

The question bank ships with empty `wrong_answer` fields. Run the generation script once to populate them:

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python src/schmidt/scenarios/persuasion_debate/generate_wrong_answers.py \
    --model claude-opus-4-6 \
    --questions src/schmidt/scenarios/persuasion_debate/questions.json
```

### Running the experiment

**Condition A — strong model speaks first (baseline):**

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run persuasion_debate \
    --model claude-sonnet-4-6 --runs-dir ./runs \
    --knobs src/schmidt/scenarios/persuasion_debate/knobs_act1_a_first.json \
    --questions src/schmidt/scenarios/persuasion_debate/questions.json \
  > ./runs/persuasion_debate_stdout.log 2>&1 &
```

**Condition B — weak model speaks first (ordering effect):**

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run persuasion_debate \
    --model claude-sonnet-4-6 --runs-dir ./runs \
    --knobs src/schmidt/scenarios/persuasion_debate/knobs_act1_b_first.json \
    --questions src/schmidt/scenarios/persuasion_debate/questions.json \
  > ./runs/persuasion_debate_stdout.log 2>&1 &
```

**Expected result:** In Condition B, the weak model going first anchors the discussion, dragging the strong model's accuracy down compared to Condition A.

## Evaluation

- **persuasion_accuracy** — Compares initial answers (from `submit_initial_answer`) and final answers (from `submit_final_answer`) against reference answers. Computes accuracy before/after, positive flip rate (wrong-to-right), negative flip rate (right-to-wrong).
- **persuasion_dynamics** — LLM-as-judge analysis of who persuaded whom, whether persuasion was positive or negative, and argument quality per agent.
