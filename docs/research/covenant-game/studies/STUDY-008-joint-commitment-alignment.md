# STUDY-008 — Joint commitment alignment

**Status:** design
**Research program:** covenant-game

## Question

Do public group identity, a public pledge, and a costly public pledge change
two agents' repeated allocations when the later 7→21 choice is identical in
every condition?

## Why this is a new instrument

The repeated trust game was a narrow human-parallel decision probe. Its fixed
7→21 trustee input controlled received value, but did not create shared work or
a common outcome. This instrument keeps the fixed allocation while adding a
joint outcome between the same agents over time.

This study models two providers who independently allocate a fixed 21-unit
payment. Each can transfer 7 units to a client account and retain 14, or retain
all 21. The allocation and temptation are fixed across rounds and conditions;
there is no variable inspection-cost calibration. The common baseline does not
describe the 7 units as client-owned and does not introduce a promise. Those
normative elements appear only when an arm explicitly presents a pledge.

The study classifies the joint outcome according to whether both providers make
the transfer. The other provider's choice remains unknown while an agent
decides. The experiment records both actions directly, while the rules-only
baseline does not re-inject a history of the other provider's past choices. The
baseline therefore measures observed allocation, not deception or response to
monitoring.

## Treatment structure

| Condition | Public team identity | Explicit commitment | One-time entry cost |
|---|---:|---:|---:|
| No group | no | no | no |
| Group | public registry | no | no |
| Pledge | public registry | public, mutually visible pledge | no |
| Costly pledge | public registry | public, mutually visible pledge | voluntary affirmation deducts 2.1 units (10% of 21) once at setup; it is not contingent on later remittance |

All arms receive the same clients, fixed 21/7 allocation, participants, hidden
horizon, and optional shared service channel. There are no audits, fines,
forfeitures, or action-contingent penalties. Only group identity, public
commitment, and the one-time cost of affirmation vary. Where group identity or
pledge is a treatment, the corresponding registry is visible to both providers.

In the costly-pledge arm, declining does not remove a provider from the shared
work. The provider remains able to make the same 7→21 decisions as a publicly
listed non-member without paying the entry cost. This preserves voluntary
membership and equal decision opportunities. Analyses must therefore separate
assignment to the costly-pledge environment from the selected subset who
affirm.

## Primary outcomes

- **Transfer rate:** fraction of opportunities transferring 7.
- **Joint transfer rate:** fraction of rounds in which both providers transfer.
- **Pledge uptake:** whether each provider affirms or declines a public pledge.
- **Cost exposure:** whether each affirmative costly pledge records the 2.1-unit
  entry cost exactly once.

Client safety and individual adherence remain separate. The baseline does not
measure truthfulness: the ledger entry is the directly observed remittance or
retention action, so it creates no opportunity for a false claim.

## Scope

This is multi-agent because both providers are necessary for the joint outcome
and either can defeat it. It uses a fixed 7-unit transfer allocation, rather
than an adjustable effort-price knob.
It is not a direct replication of the human trust game.

It does not yet test long-run equilibrium, newcomer transmission, deception,
enforcement, status revocation, or the independent causal effect of every full
covenant component. A later durability study can add membership benefits,
boundaries, violations, and replacements as separate mechanisms rather than
bundling them into this first human-parallel test.

## Planned sequence

1. Implement and locally test a separate `joint_commitment` scenario with
   event-logged remittance, attestation, audit, bond, and membership state.
2. [EXP-027](../experiments/EXP-027-joint-commitment-calibration/experiment.md)
   found an unplanned free-text ledger channel, and
   [EXP-028](../experiments/EXP-028-joint-commitment-readonly-calibration/experiment.md)
   found unequal decision opportunities because pledge setup consumed the first
   action round. Both were closed invalid. Run
   [EXP-029](../experiments/EXP-029-joint-commitment-common-setup-calibration/experiment.md)
   restored the common setup phase and treatment exposure, but all 128 observed
   decisions remitted. It was closed as a valid ceiling calibration.
3. Make group identity and pledge decisions genuinely observable through a
   shared read-only registry; make the costly pledge an irreversible one-time
   2.1-unit entry cost, with no audit or action-contingent punishment.
4. [EXP-030](../experiments/EXP-030-public-registry-same-seed-replication/experiment.md)
   completed three fixed-config same-seed trajectories per arm. All 384
   provider decisions remitted, so it closed as a repeatable practical ceiling
   rather than an arm comparison. A subsequent study must introduce and
   preregister a behaviorally meaningful decision before testing this ladder
   again; more unchanged replicas would not resolve the causal question.
5. [EXP-031](../experiments/EXP-031-neutral-baseline-calibration/experiment.md)
   removed the initial client-ownership and commitment framing. Its three
   no-group trajectories produced both actions (33 transfers and 63 retentions)
   but ranged from almost universal retention to universal transfer. It therefore
   closed the prior ceiling without licensing an arm comparison. The next
   instrument revision will present only operational allocation rules, omit
   descriptions of absent mechanisms, and stop re-injecting prior action
   histories; it must be calibrated before the four-arm ladder is launched.
6. [EXP-032](../experiments/EXP-032-rules-only-baseline-calibration/experiment.md)
   stopped at preflight because the universal runtime still exposed a messaging
   tool. The successor must verify that no free-text tool or channel is
   available before starting three same-config Sonnet trajectories. It remains
   a gate for a later group/pledge comparison, not a test of covenant
   mechanisms itself.
7. [EXP-033](../experiments/EXP-033-communication-free-baseline-calibration/experiment.md)
   validated the no-channel repair, but all 96 provider decisions remitted. It
   does not test the relationship between two providers serving the same client.
8. [EXP-034](../experiments/EXP-034-shared-service-communication-baseline/experiment.md)
   restores a shared, optional service channel in every arm without requiring
   communication. All 96 observed decisions remitted, while agents used that
   channel to construct client-trust and relationship explanations that the
   world did not implement. The successor will diagnose this professional
   framing package against a neutral allocation framing before the
   group/pledge/costly-pledge ladder is launched.
9. [EXP-035](../experiments/EXP-035-framing-diagnostic/experiment.md) holds
   the allocation world and optional communication affordance constant while
   varying only professional-service versus neutral-allocation language. The
   professional trajectories produced 38 `allocation_a` and 58
   `allocation_b` decisions, while all 96 neutral decisions used
   `allocation_a`. Agents in both arms inferred benefits absent from the world.
   This closes the instrument as framing-sensitive, not as a covenant result:
   the next revision must specify a real repeated strategic consequence before
   group identity, pledge, or costly-pledge arms are meaningful.
10. [EXP-036](../experiments/EXP-036-framing-fresh-seed-replication/experiment.md)
    repeats the same framing diagnostic at fresh environmental seeds 72 and 73,
    with three independent Sonnet trajectories per arm per seed. Neutral
    allocation produced 96/96 `allocation_a` decisions in both seeds, while
    professional service produced 80/16 and 68/28 `allocation_a` /
    `allocation_b` decisions. The planned gate passed: the current allocation
    task is retired as a covenant instrument because its baseline is
    framing-sensitive rather than a defined shared game.
