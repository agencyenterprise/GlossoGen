# STUDY-006 — Human-parallel commitment

**Status:** instrument revision needed
**Research program:** covenant-game

## Question

Across repeated interactions, does a public group, an explicit pledge, or the
human-study covenant bundle (pledge plus a 10% forfeiture) change whether
two LLM providers honor a commitment to perform a genuine inspection when
shortcutting has a fixed immediate private payoff?

## Why a new instrument

The previous team-production scenario answers a different question: the effect
of an institutional bundle with recruitment, payment promises, stale counts,
audits, refunds, bond liability, membership, and sanctions. Its mechanism-scale
outcomes have too much run-to-run variance to resolve at an affordable sample
size.

This scenario removes correctness, audit, task-price, and staffing variation.
The gross choice schedule is fixed in every condition: inspecting earns 10;
shortcutting earns 17. The primary outcome is the action recorded by the world,
not count accuracy or a self-report. The covenant condition charges 10% of each
realized reward, which scales both gross rewards and is mathematically
equivalent to a 10% forfeiture of accumulated winnings while making the cost
visible in a repeated-agent world.

This is a human-parallel commitment study, not a test of equilibrium or
institutional deterrence. A future persistent-membership experiment would ask
whether revocable access to future opportunities adds something beyond the
human-style pledge-and-forfeiture bundle.

## Conditions

| Condition | Public group | Explicit pledge | Automatic forfeiture |
|---|---:|---:|---:|
| No group | no | no | no |
| Group | yes | no | no |
| Pledge | yes | yes | no |
| Covenant | yes | yes | 10% of each reward |

## Experiments

- [EXP-025 — Human-parallel commitment instrument pilot](../experiments/EXP-025-human-parallel-commitment-pilot/experiment.md)
  implemented all four treatments as world events, but the primary joint
  inspection outcome remained at zero in all twelve runs. A successor record
  should revise the action setup before testing another seed: it must preserve
  a fixed temptation while allowing a pledge to be action-relevant and every
  round to offer the same choice.
