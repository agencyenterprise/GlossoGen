# STUDY-009 — Shared reserve commitment

**Status:** calibration
**Research program:** covenant-game

## Question

When two providers face a genuine repeated common good, do public group
identity, public pledge, and a one-time costly pledge change persistent
contribution and service continuity?

## Why this is a distinct instrument

The warehouse instrument contained a real joint task but changed an entire
institutional bundle at once. The retired `joint_commitment` instrument had a
simple 7→21 choice and the technical components for group and pledge, but its
client account had no implemented shared consequence. Agents therefore had to
invent what the action meant.

This scenario keeps the simple two-agent 21/7 choice but implements the shared
good directly. Contributions enter a public Continuity Reserve. A fixed hidden
schedule of client claims is the same in every arm. A claim is paid from the
reserve when possible; otherwise, the recurring client service ends and neither
provider receives later payments. Past actions and reserve state appear in a
public ledger only after both current decisions have been recorded.

This establishes a real repeated strategic problem before any covenant
mechanism is added. One provider can temporarily free ride on the other, while
both lose future payments if the reserve cannot meet a later common claim.

## Treatment ladder

| Condition | Public group identity | Public voluntary pledge | One-time 10% cost on affirmation |
|---|---:|---:|---:|
| No group | no | no | no |
| Group | yes | no | no |
| Pledge | yes | yes | no |
| Costly pledge | yes | yes | yes, 2.1 units |

The costly-pledge arm is the human-parallel commitment treatment. It is not a
full covenant: it intentionally has no audit, fine, forfeiture, expulsion,
replacement, or repair mechanism. Those mechanisms should be added only in a
later study after the clean commitment ladder is interpretable.

The group registry, pledge statement, pledge choice, enrollment cost, each
contribution, the reserve balance, claims, and service termination are all
implemented state transitions and event-logged. Pledge decisions and completed
round ledgers are posted to the shared service channel, so they are genuinely
observable by both providers rather than merely visible to the researcher.

## Outcomes

- **Persistent contribution:** contribution rate and contribution trajectory
  before and after each reserve claim.
- **Informal coordination:** whether providers coordinate a sustainable
  contribution pattern before any group treatment.
- **Free-riding:** retained allocations despite a continuing shared reserve
  need, reported separately from service survival.
- **Service continuity:** whether every scheduled client claim was covered and
  the service reached the hidden horizon.
- **Pledge uptake and cost exposure:** public affirm/decline decisions and
  actual 2.1-unit deductions.

Each whole trajectory, not a round within it, is the independent unit. The
first model is Claude Sonnet 5. For a fixed model, seed, condition, prompt,
claim schedule and all other knobs, run three independent trajectories before
interpreting a behavioral pattern. Use fresh matched seeds only after the
initial same-config calibration passes.

## Sequence and guardrails

1. [EXP-037](../experiments/EXP-037-shared-reserve-baseline-calibration/experiment.md)
   validates the no-group baseline. It tests whether the common good, public
   ledger, and shared consequence produce neither a universal contribution
   ceiling nor universal retention floor.
2. Only if EXP-037 passes its prespecified variation and instrumentation gates,
   run the four-condition group → pledge → costly-pledge ladder with three
   independent trajectories per exact configuration.
3. Make at most one substantial revision to the reserve-claim schedule. If the
   baseline remains a universal floor or ceiling after that revision, retire the
   instrument rather than tuning toward a desired covenant result.
4. Do not infer that contribution is moral alignment. The causal question is
   whether the implemented institutional exposure changes observable
   contribution persistence and continuity under the same common-good world.
