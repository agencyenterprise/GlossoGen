# Persuasion Debate

Two agents debate trivia questions to study how LLMs handle persuasion. Based on the Persuasion-Balanced Training (PBT) paper by Stengel-Eskin et al. (2025).

## Modes

### Misinformation (Section 4.1)
An adversary agent tries to convince a target agent to abandon a correct answer. The adversary uses a configurable persuasion strategy (logical, emotional, or credibility-based). Measures resistance to negative persuasion.

### Balanced (Section 4.2)
Half of the rounds test resistance to negative persuasion (target starts correct, adversary pushes wrong). The other half test acceptance of positive persuasion (target starts wrong, partner pushes correct). Roles alternate every other round.

### Debate (Section 4.3)
Both agents answer genuinely with no adversarial role. Use model_overrides in knobs to pair models of different strengths. Measures team accuracy, order dependence, and whether the stronger model pulls the weaker one up.

## Agents

- **Agent A** — First or second responder depending on `agent_order` knob. In misinformation mode, defaults to target role.
- **Agent B** — Complementary role. In misinformation mode, defaults to adversary role.

## Channels

- **debate** — Single shared channel for all discussion.

## Tools

- `send_message` — Send a message to the debate channel
- `pass_turn` — Pass when nothing to add
- `submit_final_answer(answer)` — Submit a final answer for the current question

## Turn Structure

Each round (one question):
1. First agent states initial answer (cannot pass)
2. Second agent responds (cannot pass)
3. Discussion: agents alternate until both pass in a full rotation or max_turns_per_round is reached
4. Next round begins

## Round Injections

Each round, both agents receive the question text. Injection content varies by mode:
- **Target**: receives the question and (in some modes) a seeded initial answer
- **Adversary**: receives the question and the wrong answer to argue for
- **Debater**: receives the question and whether they answer first or second

## Knobs

| Knob | Values | Description |
|------|--------|-------------|
| mode | misinformation, balanced, debate | Evaluation mode |
| agent_order | a_first, b_first | Which agent answers first |
| round_count | int | Number of questions (rounds) |
| max_turns_per_round | int | Turn cap per round |
| persuasion_strategy | logical, emotional, credible | Adversary's approach (misinformation mode) |
| model_overrides | dict | Per-agent model overrides for pairing different strengths |

## Question Bank

A `questions.json` file with 100 TriviaQA questions is checked in. To refresh or customize the question set, run the download script:

```bash
pip install datasets
python src/schmidt/scenarios/persuasion_debate/download_triviaqa.py --count 100
```

This streams questions from the TriviaQA validation split (unfiltered config) and writes them to `questions.json` in this directory. The `--count` flag controls how many questions to include. The `--output` flag overrides the output path.

The `datasets` library is only needed for this script — it is not a runtime dependency of the scenario.

## Evaluation

- **persuasion_accuracy** — Compares initial and final answers against reference answers. Computes accuracy before/after, positive flip rate (wrong→right), negative flip rate (right→wrong), and misinformation rate.
- **persuasion_dynamics** — LLM-as-judge analysis of who persuaded whom, whether persuasion was positive or negative, and argument quality per agent.
