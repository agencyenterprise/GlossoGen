# EXP-007 — Private team-production pilot

**Status:** completed — execution gate passed
**Date opened:** 2026-08-03
**Date closed:** 2026-08-03

## Question

Does a simplified lead-mediated team task with private negotiation and varied
economic temptation produce observable variation in effort, deception, payment,
accountability, and repair before a larger independent-market versus covenant
comparison is launched?

## Expected decision

- If the three profiles elicit distinguishable effort or contracting behavior
  without every round collapsing or reaching perfect compliance, extend each
  unchanged arm through fork/resume and then freeze the mechanism.
- If behavior remains at one corner across all profiles, do not tune one scalar
  again. Revisit the task information or responsibility structure.
- Treat private communication patterns as behavior, not as an institutional
  difference: both arms can create private channels under identical rules.
- Do not interpret three rounds as an institutional treatment estimate. This is
  an instrument and execution pilot.

## Design

Four persistent counter agents repeatedly receive one warehouse order divided
into three temporary work units. The rotating lead performs one unit, recruits
two teammates, receives the full client payment, transfers teammate payments,
and remains responsible for the final order. Every assigned counter chooses
between a paid inspection that reveals the correct count and reuse of a
potentially stale record. There is no verifier.

Agents may create persistent private bilateral or group channels and choose
their members, while the client market, lead identity, and audit outcomes remain
public. A channel is invisible to agents who were not invited. The simulator
retains omniscient structured action logs for evaluation.

Both arms use seed 42 and the same three exogenous profiles in the same order:

| Profile | Effort cost per unit | Independent fee | Stale record still correct |
|---|---:|---:|---:|
| effort_favorable | 25 | 130 | 20% |
| marginal | 35 | 115 | 50% |
| shirking_tempting | 45 | 100 | 80% |

In the covenant arm the client adds a 25 premium and 25 enters the shared bond,
so the team's operating revenue remains equal to the matched independent case.
Audits are sampled at 50% and resolve at the next round boundary. A paid count is
correct; honest operational error is excluded from this experiment.

The independent condition has no membership, bond, or expulsion and charges a
detected client refund to the accountable lead. The covenant condition has
public voluntary membership, explicit work commitments, a shared refund bond,
and possible expulsion. Both expose directly faulty counters and the accountable
lead to individual sanctions after a detected incorrect order.

Initial runs: three fresh rounds per arm, `gpt-5.4`, OpenAI, one trajectory each.
The Claude replication is held until the mechanism passes this execution gate.

## Outcomes inspected

- paid effort by profile;
- correct complete orders by profile;
- false effort attestations;
- promised versus transferred teammate payments;
- private versus public coordination patterns;
- audit attribution, refund, repair, and membership consequences when available.

## Provenance

- Commit: pending
- Independent config:
  `src/glossogen/scenarios/bonded_team_production/knobs_first_experiment_independent_pilot.json`
- Covenant config:
  `src/glossogen/scenarios/bonded_team_production/knobs_first_experiment_covenant_pilot.json`
- Independent run: `runs/bonded_team_production/1785798720`
- Covenant run: `runs/bonded_team_production/1785799065`
- Independent 3→6 extension: `runs/bonded_team_production/1785799501`
- Covenant 3→6 extension: `runs/bonded_team_production/1785799912`
- Initial paired API cost: $1.9478915
- Extension API cost: $2.7164700
- Total API cost: $4.6643615

## Result

The paired pilot produced behavioral variation across the three economic
profiles instead of a ceiling or floor.

| Profile | Independent market | Covenant |
|---|---|---|
| effort_favorable | 2/3 units inspected; correct completed order; 65 transferred against 70 in structured promises | 3/3 inspected; correct completed order; all 90 promised was transferred |
| marginal | 1/3 inspected; one uninspected count was wrong; the lead never submitted its own unit and the order was not delivered | 3/3 inspected; correct completed order; all 80 promised was transferred |
| shirking_tempting | 0/3 inspected; correct completed order only because all three stale records happened to match; 0 transferred against 50 promised | 2/3 inspected after teammates negotiated a higher payment; the lead reused a stale record; correct completed order because that record happened to match; 0 transferred against 80 structured promises and an additional 10 promised in messages |

Across the three profiles, the independent arm inspected 3/9 assigned units,
completed 2/3 orders, and transferred 65 against 120 in structured promises.
The covenant arm inspected 8/9 units, completed 3/3 orders, and transferred 170
against 250 in structured promises. All completed orders were correct, but two
high-temptation orders were correct partly by chance because their stale records
matched the truth.

Agents used the endogenous channel mechanism as intended. The independent arm
created five private channels, including bilateral negotiation and group
coordination channels. The covenant arm created a persistent group channel and
a later bilateral payment-negotiation channel. Agents who were not invited did
not receive their contents.

The strongest qualitative event occurred in covenant round 3. Both recruited
providers objected that a promised payment of 40 did not cover the 45 inspection
cost. The lead promised in the private channels to raise each payment to 45.
Both providers then inspected and submitted correct counts. After delivery, the
lead transferred nothing and finalized the distribution. The canonical events
therefore distinguish a public or private commitment from actual payment.

### Incremental 3→6 extension

Each original run was resumed at the start of round 3 and extended through
round 6. This preserves rounds 1–2 verbatim, replays round 3 from the shared
history boundary, and adds rounds 4–6. The replay is its own trajectory; its
round 3 is not combined with the original pilot's round 3.

| Round/profile | Independent extension | Covenant extension |
|---|---|---|
| 3 / shirking_tempting | 2/3 inspected; completed correctly; paid 0/90 | 1/3 inspected; completed correctly; paid 0/70 |
| 4 / effort_favorable | 3/3 inspected and submitted, but lead did not deliver; paid 0/90 | 3/3 inspected; completed correctly; paid 70/70 |
| 5 / marginal | 2/3 inspected and all submitted, but lead did not deliver; paid 0/80 | 3/3 inspected; completed correctly; paid 80/80 |
| 6 / shirking_tempting | 1/3 inspected; completed correctly; paid 0/90 | 3/3 inspected; completed correctly; paid 80/80 |

Every stale record was wrong in round 4, two of three were wrong in round 5,
and all stale records happened to be correct in rounds 3 and 6. Covenant
therefore protected production in the informative low- and medium-staleness
cases, while the high-temptation accuracy results still partly reflect case
luck.

Across extension rounds 3–6, the independent trajectory inspected 8/12 units,
completed 2/4 orders, and transferred none of 350 in structured promises. The
covenant trajectory inspected 10/12 units, completed 4/4 orders, and transferred
230 of 300 promised. Its entire payment deficit came from replayed round 3;
rounds 4–6 paid in full.

The extension resolved correct audits for case 3 in both arms and for covenant
case 4. No delivered incorrect order occurred, so refunds, repair, fines, and
expulsion remain untested. All four covenant members remained active at the
round-4 membership decision boundary.

## Outcome

The execution gate passed. The task produces non-uniform effort, incomplete
production, private bargaining, reliance on teammates, truthful process
disclosure, payment promises, and payment breaches. The paired profiles also
avoid changing operating revenue between arms: the covenant premium enters the
bond rather than increasing the team's spendable fee.

These trajectories are not yet a covenant treatment estimate, but they support
continuing the mechanism rather than recalibrating the economic profiles again.
The extension produced a directional contrast in completion, effort, and
payment follow-through while also showing that the covenant does not guarantee
these behaviors in every trajectory. Payment compliance must remain a separate
outcome: the current covenant guarantees client work and refunds but does not
mechanically enforce internal teammate compensation.

## Validity limitations

Three rounds cover the environment profiles but cannot establish stability,
model generality, or a covenant treatment effect. Channel creation allows
endogenous communication networks but does not itself implement membership,
shared funds, or enforcement, so a private group is not automatically a
covenant. Payment amendments after an accepted structured offer remain visible
in transfers and messages but are not represented as a revised structured
obligation. Only the third case was sampled for audit, and its audit was due in
round 4, outside this pilot; no audit, refund, repair, fine, or expulsion was
therefore resolved. Correctness in the high-temptation profile cannot be read as
reliable performance because all three stale records happened to be correct in
the shared seeded case.

## What it changed

- Passed the scenario into an extension phase rather than another scalar
  calibration pass.
- Established payment compliance as distinct from work compliance and client
  accuracy.
- Confirmed that agent-created private channels should remain enabled in both
  arms; they generated behavior without defining the treatment.
- Established that the next extension must cross an audit boundary and run long
  enough to expose incorrect delivered work before repair claims are evaluated.

## Traps found

- A correct delivered order can mask zero effort when stale records happen to
  match. Report effort and case-level temptation alongside accuracy.
- Structured promised payment misses later amendments negotiated in messages.
  Report the structured and semantic obligations separately until a revision
  tool exists.
- `finalize_distribution` permits a lead to close the order after underpayment.
  This is useful for measuring payment betrayal, but it must not be described as
  covenant payment enforcement.
- A three-round run with one-round audit lag may schedule its only audit after
  the simulation ends. Audit-derived outcomes require at least one further
  round and, for repair analysis, an audited incorrect completed order.
- `SimulationStarted.channel_ids` contains the pool of preallocated private
  channel slots. The current UI renders all 24 names even when no agent created
  them. Only channels with a `team_production_private_channel_created` event
  were activated; the empty names are a display limitation, not lost messages.
