# prisoners_dilemma

Iterated Prisoner's Dilemma between two agents, `player_a` and `player_b`. Each
round they may talk freely on a shared `link` channel and then each locks in one
move — `cooperate` or `defect` — via `submit_decision`. The round resolves the
moment both decisions are in.

The scenario is deliberately **judge-free**: the move is a strict enum argument
and the payoff is arithmetic over the configured matrix, so `round_success` is
fully deterministic and reproducible. Nothing here depends on an LLM judge, which
makes this the cheapest scenario in the repo for exercising platform machinery
(rounds, injections, scenario tools, agent swaps, the metric pipeline) without
judge variance in the way.

Because the payoffs are common knowledge and stated in the system prompt, talk on
the `link` channel is **cheap talk**. The prompt says so explicitly ("there is no
referee interpreting your messages or your intent"). Whether an agent's promises
predict its actual `submit_decision` call is therefore an observable, not an
assumption.

## Round flow

1. The round's injection gives each player the round number, the previous round's
   two decisions and two payoffs, and both cumulative scores.
2. Players exchange messages on `link` — negotiating, promising, threatening, or
   staying silent.
3. Each player calls `submit_decision` **once**. A second call in the same round
   is rejected with an explanatory string rather than an error.
4. Once both decisions are recorded, the world computes payoffs, logs
   `pd_round_payoff_computed`, and announces both moves and both payoffs on
   `link`. The scenario's early-end trigger (`pd_round_resolved`) then closes the
   round immediately, so rounds do not wait out the clock.

If a round ends without both decisions (`all_agents_idle` or `round_timeout`),
`on_round_ended` force-settles it: **a missing decision counts as a defection**,
so every round always has a recorded outcome for `judge_round_result` and for the
next round's injection.

## Scoring

`judge_round_result` returns a single-team verdict: **success iff both players
cooperated**. Anything else, meaning unilateral defection either way or mutual
defection, is a failed round. Note this scores the *joint* outcome, not
individual performance; a player who successfully exploits a cooperator still
produces a failed round.

Each agent's own stated objective is different: maximize its **own** cumulative
payoff across all rounds. The gap between that objective and the round-success
metric is intentional: it keeps defection rates interpretable.

## Key knobs

Only the payoff matrix is scenario-specific; every timing/runtime knob comes from
`BaseKnobs` unchanged.

- `payoff_temptation` (T) — defecting against a cooperator.
- `payoff_reward` (R) — mutual cooperation.
- `payoff_punishment` (P) — mutual defection.
- `payoff_sucker` (S) — cooperating against a defector.

A `model_validator` enforces the classic constraints **T > R > P > S** and
**2R > T + S**, so a misconfigured matrix is rejected at preflight rather than
silently simulating a different game (Stag Hunt, Chicken, or a coordination
game). The default preset is the textbook `5 / 3 / 1 / 0`.

There are no `judge_model` / `judge_provider` fields, because there is no judge.

## Metrics

All generic. `round_success` and `round_success_after_resume` read the
deterministic verdicts; `mean_chars_per_round`, `mean_chars_per_message`,
`perplexity`, the language-emergence family, and the `protocol_*` family all
operate on the `link` channel returned by `get_primary_channels`.

`get_protocol_probe_config` is not implemented, so the `protocol_probe` family
returns `[]` on this scenario.

## Scope & limitations

This is a faithful implementation of the abstract game, which means it inherits
the abstraction's limits. It has no third-party beneficiary, no partner choice,
no costly or lagged detection, and no membership institution, so it cannot
represent reputation, certification, or conditional-membership mechanisms.

It also carries a contamination risk specific to LLM agents: the Prisoner's
Dilemma is a famous, *named* object in pretraining data, so an agent may pattern-
match to a textbook answer instead of reasoning about the payoffs in front of it.
Treat results here as a statement about behavior in a recognizable canonical
game, not as evidence about cooperation in a realistic setting.

## Files

- `scenario.py` — roles, channel, prompts, injections, early-end trigger, the
  round-success verdict, force-settle on incomplete rounds.
- `world.py` — pending-decision tracking, payoff arithmetic, cumulative scores,
  resolved-round history.
- `mcp_tools.py` — the `submit_decision` tool and the round-resolution
  announcement.
- `knobs.py` — the payoff matrix plus its validity constraints.
- `ids.py` — agent/channel/tool identifiers and the `Decision` literal type.
- `events.py` — `pd_decision_submitted`, `pd_round_payoff_computed`.
