# pledge_breach

One live provider allocates to a shared reserve against a **scripted partner** that
publicly affirms a pledge and then breaks it. The question is not how much the
provider contributes — it is what the provider does after watching a committed
counterparty defect.

## Why this scenario exists

`shared_reserve_commitment` was retired after five batches. Its `retain` action
never denoted free-riding: with two live agents, a disclosed claim amount and a
visible reserve, the pair negotiated a contribution rotation and harvested
provable slack. Contributing also dominated by roughly 45 to 1, so no
institutional treatment could move the outcome.

This scenario removes all three causes:

| Cause of the previous ceiling | Fix here |
|---|---|
| Two live agents coordinate a rotation | The partner is world state on a fixed script; there is nobody to negotiate with |
| Sufficiency is computable, so retention is provably safe | The claim amount is withheld, so no moment is provably safe |
| Contributing dominates ~45:1 | The claim is placed at the material break-even point (see Calibration) |

It also mirrors the human covenant study's own control: that study used
**simulated partners** and held the received offer constant, calling this "a
genuine advantage over designs that pair participants live."

## World

Two parties, one of them real.

- `provider_a` — the only live agent. Holds an endowment, receives
  `round_payment` each active round, and chooses `contribute`
  (`contribution_amount` to the reserve) or `retain` (keep everything).
- `provider_b` — **not an agent.** Its action each round is read from
  `partner_retain_rounds`. Identical in every condition.

A single client claim of `claim_amount` falls due at `claim_round`. Covered, the
service continues; uncovered, it ends immediately and no later round payments
are issued.

The provider is **sealed**: it holds only its structured actions, no
`send_message` and no `read_channel`. Everything it needs — the partner's last
action, the reserve, the standing pledge record, the claim outcome — arrives in
the per-round injection. Nothing depends on the agent choosing to read a
channel, which a smoke test showed is unreliable.

## Conditions

A 2×2 over commitment and cost, plus a baseline:

| Condition | Group registry | Public pledge | Membership cost |
|---|---|---|---|
| `no_group` | — | — | — |
| `group` | yes | — | — |
| `pledge` | yes | yes | — |
| `cost` | yes | — | yes |
| `covenant` | yes | yes | yes |

`cost` is the cell the human study **cannot** supply. Its own authors record
that Group 1 differs from Group 2 in two ways at once — a pledge and a 10%
forfeiture — and that the design cannot separate them. A fee carrying no
commitment statement separates them.

The cost is charged on affirmation where a pledge exists, and automatically at
setup where it does not.

## The breach

In pledge-bearing conditions the partner affirms the pledge during setup and
then retains on its scripted rounds. The provider is told the partner's action
every round and the standing pledge record every round, so the contradiction is
legible — but the scenario never labels it a breach. The interpretation is left
to the provider.

`PledgeBreachPartnerBreached` is written to the log for analysis only and is
never shown to the provider. It makes the before/after split trivial to compute.

The partner's behaviour is **identical across all five conditions**. Only whether
it had committed changes. Same action, different meaning.

## Calibration

`claim_amount` must sit strictly between what the partner accumulates alone and
what both can accumulate by the claim round. The knobs model rejects anything
outside that window, because outside it the outcome cannot respond to the
provider's choices at all — the failure that wasted EXP-041 (claim too high,
contribution forced) and EXP-038/039/044 (claim too low, slack harvested).

Place the claim at the **material break-even point**: the cost of the
contributions the provider must make should equal the value of the rounds the
surviving service still pays. The bundled presets use

```
round_count 17, claim_round 14, partner retains on [4, 5, 9, 12, 15, 16]
  partner alone contributes    9 rounds ->  63 units
  service survival is worth   21 x 3    ->  63 units
  provider break-even          9 of 13 contributions -> 63 units
  => claim_amount = 126, leaving the provider 4 rounds of slack
```

Neither contributing nor retaining dominates. That is the point: only at the
margin can a treatment show.

## Outcomes

- **Response to breach (primary):** the provider's contribution rate before
  versus after the partner's first visible breach, compared across conditions.
  This is where `retain` finally means reciprocity rather than optimisation.
- **Service continuity:** whether the claim was covered.
- **Pledge uptake and cost exposure:** affirm/decline and the real deduction.
- **Post-claim behaviour:** rounds after the claim resolves carry no remaining
  stake, so what the provider does there tests whether the pledge is honoured
  for its own sake.

Channel metrics — throughput, perplexity, the language judges — are **not
meaningful** here. The provider holds no communication tools, so the record
carries only scenario-authored text.

## Validity note to carry into any record

This is an **extension** of the human covenant study, not a replication. That
study measures trust and reciprocity against a neutral simulated partner; this
adds commitment breach by the counterparty, which it never tested. Numbers from
the two are not directly comparable.

The provider is told a second provider exists. It does not. The rationale is the
same control the human study used, and it must be stated in any experiment
record rather than left implicit in the code.
