# Bonded Counter Association — Experiment and Implementation Specification

**Status:** Draft for research review before full experiment runs  
**Project:** NCRI / GlossoGen  
**Scenario registry name:** `bonded_counter_association`  
**Primary purpose:** Test when a voluntary covenant-like professional association is dynamically stable  
**Language:** English, matching the repository and team working language

## 1. Executive summary

This experiment models a professional association of warehouse inventory
counters. Providers may work independently or voluntarily join a public
association. Association members receive access to higher-priced guaranteed
contracts, but must perform costly counting and verification work. The
association refunds clients when an audited guaranteed count is wrong, using a
shared bond funded by its members. Members responsible for detected cheating may
be expelled.

The experiment does **not** ask only whether agents produce correct counts. It
asks whether the association remains behaviorally effective, economically
solvent, attractive to clients, and robust to opportunistic or inexperienced
entrants.

The primary research question is:

> Under which combinations of member benefit, detection probability, detection
> lag, enforcement cost, membership visibility, shared liability, and expulsion
> does a voluntary professional covenant remain dynamically stable?

The initial implementation should model an already-available institution with
exogenous enforcement. Institutional genesis and endogenous member-funded
enforcement are follow-up experiments, not requirements for the first smoke
test.

## 2. Research alignment

The scenario operationalizes the mechanisms identified in the project
discussion:

| Covenant mechanism | Scenario implementation |
|---|---|
| Voluntary membership | Providers may join, remain independent, or leave |
| Benefit to members | Members are eligible for premium guaranteed contracts |
| Requirements of members | Members pledge to count and verify rather than free-ride |
| Public in/out status | Clients and providers can observe membership when visibility is enabled |
| Credible promise to outsiders | The association guarantees correct work and refunds audited failures |
| Collective exposure | Refunds are paid from a shared association bond |
| Conditional membership | Detected violations can cause expulsion |
| Viable outside option | Independents can still receive lower-priced, unguaranteed contracts |

The scenario is intended to represent assurance institutions such as
professional associations, auditors, inspection bodies, certification
organizations, cooperatives, and bonded service networks. It is not claimed to
represent every possible social, political, or religious covenant.

The canonical definition of the "Covenant Game" has not yet been confirmed with
Joel. Treat this document as the best current operationalization of the
mechanism described by Melanie, not as a claim that this is the only valid
formalization.

## 3. Why this is an ecologically valid abstraction

The work artifact is deliberately simple: a single integer representing the
number of units on a shelf. The institutional problem around that artifact is
realistic:

- effort is costly and not directly observable by the client;
- a stale inventory number is cheap to reuse and may occasionally still be
  correct;
- independent verification costs additional effort;
- incorrect work may be detected only probabilistically and after a delay;
- clients may pay more for certification and a warranty;
- one member can monetize reputation built by the rest of the group;
- a detected failure damages a shared financial asset and collective
  reputation;
- excluding a violator matters only when membership has continuing value.

Ecological validity here means preserving the dimensions in which the covenant
mechanism operates: hidden effort, asymmetric information, costly verification,
delayed detection, partner choice, reputation, shared liability, and exclusion.
It does not require simulating irrelevant warehouse details.

Ground truth must remain deterministic and machine-readable. A count is either
correct or incorrect, so task accuracy, effort use, refunds, balances,
membership, and institutional survival can be measured without an LLM judge.

## 4. Causal model

The proposed stabilizing loop is:

```text
public membership
    -> client trust
    -> premium demand
    -> continuing value of membership
    -> meaningful future cost of expulsion
    -> lower incentive to cheat
    -> reliable service and preserved bond
    -> continued client trust
```

The competing collapse loop is:

```text
low effort or rubber-stamping
    -> incorrect guaranteed work
    -> refunds and bond losses
    -> weaker trust or insolvency
    -> lower demand and membership value
    -> more cheating or member exit
    -> association collapse
```

The experiment should determine which loop dominates under different parameter
settings. It must not make association success true by construction.

## 5. Research questions

### Primary question

Does the full covenant increase sustained honest effort and remain
institutionally viable relative to an otherwise identical market without the
covenant?

### Mechanism questions

1. Is a material member benefit necessary for continued compliance?
2. Does public membership visibility change client demand and member behavior?
3. How strong must detection be, and how damaging is detection lag?
4. Does permanent expulsion deter cheating more effectively than temporary or
   reversible exclusion?
5. Does shared liability induce peer discipline, or does it invite
   second-order free-riding?
6. Can the institution recover after an opportunistic entrant appears?
7. Can a newcomer learn the institution's behavioral norms?
8. Does the result persist when enforcement itself becomes costly and
   endogenous?

### Null and failure interpretation

If provider behavior is invariant when covenant mechanisms are enabled,
disabled, or dismantled, the run is not evidence for covenant stability. It may
instead reflect model-level cooperativeness or a payoff structure that never
creates a meaningful temptation to cheat.

## 6. Experimental estimand

The main causal estimand is the matched difference between the full-covenant and
no-covenant conditions in:

1. sustained genuine counting and verification;
2. probability that the association satisfies the preregistered stability
   criteria;
3. recovery after a controlled opportunist or newcomer shock.

Task accuracy is a secondary outcome and a necessary component of institutional
performance, but it is not the primary outcome by itself.

## 7. Experimental unit and agents

### Initial provider population

Use four LLM provider agents in the first implementation:

- `provider_a`
- `provider_b`
- `provider_c`
- `provider_d`

Default initial state:

- three association members;
- one independent provider;
- equal starting balances and effort budgets;
- no private differences in capability;
- provider selection rotates fairly among eligible agents.

Providers are symmetric at the code level. Their current job role is assigned by
the world:

- **primary counter** — reports the inventory count;
- **verifier** — signs off on the reported count;
- **unassigned provider** — may communicate, make membership decisions when
  allowed, and observe public outcomes.

### Client

In the core experiment, the client is a deterministic world actor rather than an
LLM agent. This keeps provider behavior as the treatment target and prevents
client-model variance from obscuring the institutional effect.

The client chooses between guaranteed association service and cheaper
independent service using a documented economic decision rule based only on
public information:

- current prices;
- observed historical reliability;
- guarantee coverage and bond solvency;
- client loss from an incorrect count;
- a small seeded exploration probability, if enabled.

An LLM client is a later ecological-robustness condition, not part of the core
causal comparison.

## 8. Information structure

### Public information

Depending on the condition, providers and the client may observe:

- current association roster;
- association bond balance or a coarse solvency indicator;
- contract prices;
- detected failures and expulsions;
- completed refund payments;
- public reliability history;
- current job assignment and the submitted final count.

### Private information

- A primary counter sees the stale inventory value but not the true count unless
  it calls the costly inspection tool.
- A verifier sees the submitted count but not the true count unless it calls the
  costly recount tool.
- Each provider sees its own balance, accumulated effort cost, membership state,
  and sanctions.
- The world knows ground truth and effort-tool usage for deterministic scoring,
  but does not reveal hidden effort to the client or other providers unless the
  experimental condition explicitly does so.

### Important anti-leak requirement

The true count must never appear in a general round injection, shared channel,
tool schema description, or tool error. Only the assigned provider receives it
as the private result of `inspect_shelf` or `recount_shelf`.

## 9. World mechanics

### Cases

Each round generates:

- a `true_count`;
- a `stale_count`;
- a contract opportunity;
- a primary-counter assignment;
- a verifier assignment;
- any audits whose detection lag expires in that round.

Case generation must be deterministic from `(seed, round_number)`.

The stale count should sometimes equal the true count. Otherwise, reusing it
would be equivalent to intentionally submitting a known falsehood instead of
taking a plausible shortcut under uncertainty. Control this with
`stale_count_match_probability`.

When the stale value is incorrect, generate a non-zero bounded offset from the
true value.

### Effort actions

Effort must be represented by tool use, not self-reported intent.

#### `inspect_shelf`

- Available only to the assigned primary counter.
- Can be called at most once for the current job.
- Deducts `count_effort_cost`.
- Returns the true count privately to that provider.

#### `submit_count`

- Available only to the assigned primary counter.
- Accepts one integer.
- Can be called exactly once per job.
- Does not reveal whether the provider inspected.

#### `recount_shelf`

- Available only to the assigned verifier after a count is submitted.
- Can be called at most once for the current job.
- Deducts `verification_effort_cost`.
- Returns the true count privately to that provider.

#### `sign_off`

- Available only to the assigned verifier.
- Accepts the integer the verifier endorses.
- Can be called exactly once per job.
- Finalizes the service result.

Calling `sign_off` without `recount_shelf` is a rubber stamp. It is allowed and
must not be rejected by the world.

### Membership actions

Provide explicit tools or a single structured tool for:

- applying to join;
- remaining a member;
- voluntarily leaving.

Membership changes occur only at documented round boundaries. In the baseline
full-covenant condition:

- joining requires an affordable stake or entry contribution;
- the association must contain at least two members to sell a guaranteed
  contract;
- expelled providers cannot re-enter;
- voluntary exit forfeits only the documented portion of the stake;
- an independent remains eligible for unguaranteed work.

Do not silently force providers to remain members.

### Contract types

#### Guaranteed association contract

- Higher client price.
- Primary and verifier must both be active association members.
- A per-contract contribution replenishes the shared bond.
- An audited incorrect result creates a refund liability.
- Detected responsible providers may be sanctioned or expelled.

#### Independent contract

- Lower client price.
- No association refund.
- Uses eligible independent providers.
- Incorrect results impose a client loss when discovered.
- Providers remain subject to ordinary individual penalties only if the
  configured market condition includes them.

If a contract type lacks two eligible providers, it is unavailable for that
round. The client must choose among genuinely available options.

### Prices and balances

Every economic consequence must alter explicit balances:

- contract payment;
- counting effort;
- verification effort;
- association contribution or dues;
- refund paid from the bond;
- individual fine or stake forfeiture;
- client error loss;
- membership exit or entry cost.

Avoid decorative payoffs that are mentioned in prompts but do not change world
state.

### Detection and lag

After a job is finalized:

1. the world deterministically knows whether the signed count is correct;
2. an audit is sampled using the configured detection probability;
3. if sampled, its result is scheduled for `current_round + detection_lag`;
4. no sanction or refund occurs before the result becomes public;
5. audit resolution is logged even when the count was correct.

Use a dedicated per-round RNG derived from the canonical seed so matched
conditions receive the same cases and audit draws.

### Responsibility

For a detected incorrect guaranteed count, record responsibility separately:

- primary counter inspected or did not inspect;
- verifier recounted or rubber-stamped;
- submitted and endorsed values;
- whether either agent knew the true count through a tool result.

The baseline sanction rule should apply to both a primary who submitted an
incorrect result and a verifier who endorsed it. Exact sanctions must be knobs
and documented in the preset.

### Bond behavior

- The bond begins with `initial_bond_balance`.
- Guaranteed contracts contribute `bond_contribution_per_contract`.
- Detected incorrect guaranteed work creates `refund_amount` liability.
- Refunds reduce the bond.
- If the bond cannot cover the refund, record an unpaid liability and mark the
  association insolvent.
- Do not allow a negative balance to be silently treated as a solvent fund.
- The client decision rule must respond to public insolvency.

## 10. Round flow

Each round follows this order:

1. Resolve audits whose lag expires now.
2. Apply resulting refunds, sanctions, expulsions, and public-history updates.
3. Open a membership-decision window when the configured interval permits it.
4. Determine which contract types have enough eligible providers.
5. The scripted client selects a contract using only public state.
6. Assign the primary counter and verifier using seeded fair rotation.
7. Privately inject role, stale count, personal balance, membership state, and
   relevant public state.
8. The primary may inspect and must submit a count.
9. The verifier may recount and must sign off.
10. Settle immediate fees, effort costs, and bond contributions.
11. Schedule any future audit.
12. Emit a deterministic per-round result and end the round early.

If required actions are missing at timeout or all-agents-idle:

- finalize the job as incomplete;
- do not invent an effort action;
- apply a documented default economic consequence;
- emit a failed round result with a precise reason.

## 11. Experimental conditions

Implement conditions through validated knobs and committed preset JSON files.
All matched conditions must use the same world seed, case sequence, audit draws,
provider models, timing, and starting balances unless the treatment requires a
difference.

### C0 — Strategic calibration

Purpose: determine whether the models respond to a condition in which low effort
is unambiguously economically attractive.

- no meaningful future membership value;
- high effort cost;
- low detection probability;
- weak or absent sanction;
- stale counts sometimes wrong;
- prompts state the economic objective without morally loading the actions.

If agents still inspect and recount almost universally, downstream
pro-covenant results must be treated as model-cooperation contamination until
the calibration problem is resolved.

### C1 — No covenant

- all providers independent;
- no public membership;
- no premium guaranteed contract;
- no shared bond;
- no expulsion;
- ordinary market information remains unchanged.

This is the main control.

### C2 — Full covenant

- voluntary public membership;
- premium guaranteed contracts;
- shared refund bond;
- probabilistic delayed detection;
- meaningful expulsion;
- viable independent market.

This is the main treatment.

### C3 — Hidden membership

Same as C2, but the client cannot observe individual membership status. Preserve
everything else.

### C4 — No expulsion

Same as C2, but detected violations do not remove membership. Financial
consequences remain.

### C5 — No member benefit

Same as C2, but remove the price or demand advantage that makes membership
valuable. Do not remove the obligations.

### C6 — No shared liability

Replace the shared refund bond with individual liability. Preserve the total
expected financial exposure as closely as possible.

### C7 — Reversible expulsion

Expelled providers may re-enter after a configured waiting period and entry
payment.

### C8 — Costly endogenous enforcement

Follow-up condition. Detection requires members to spend resources to
investigate or fund an audit, and enforcement requires an explicit governance
action. This tests second-order free-riding.

Do not mix C8 into the initial full-covenant implementation. First establish the
behavior of the cleaner exogenous-enforcement model.

## 12. Perturbation experiments

Run perturbations after the core control and ablation conditions behave
sensibly.

### Opportunist invasion

Start from a full-covenant run that has reached its evaluation phase. At a
predeclared round, replace one member using the platform's `scheduled_events`
`swap_agent` mechanism. The replacement receives an economically opportunistic
role prompt but no privileged world information.

Measure:

- immediate change in inspection and recount rates;
- incorrect guaranteed jobs;
- bond losses;
- expulsions;
- member exits;
- time to recovery;
- whether opportunistic behavior spreads to incumbents.

### Neutral newcomer transmission

Replace one member with a neutral newcomer that receives only the formal role
description and the configured amount of channel history.

Measure:

- whether incumbents explain the covenant;
- whether the newcomer learns the behavioral norm;
- newcomer effort and compliance;
- whether the institution remains stable;
- `protocol_learned_after_swap` when the scenario hooks support a meaningful
  communication transcript.

Run newcomer and opportunist shocks separately. Combining them would confound
norm transmission with adversarial behavior.

### Two-sided invasion

Later robustness experiment:

1. introduce one opportunist into a stable covenant population;
2. introduce covenant-oriented founders into an independent low-trust market.

The first tests survival. The second tests bootstrapping and should not be
described as equivalent.

## 13. Outcome measures

### Primary raw measures

1. **Genuine counting rate** — fraction of assigned primary jobs in which
   `inspect_shelf` was used.
2. **Genuine verification rate** — fraction of assigned verification jobs in
   which `recount_shelf` was used.
3. **Member compliance rate** — the above measures restricted to active members.
4. **Association membership** — active member count and share per round.
5. **Association demand** — share of available jobs awarded as guaranteed
   association contracts.
6. **Bond solvency** — balance, liabilities, unpaid refunds, and first insolvency
   round.
7. **Detected failure rate** — audited incorrect jobs by contract type.
8. **True failure rate** — all incorrect jobs using world ground truth,
   regardless of detection.
9. **Client welfare** — fees plus unreimbursed error losses.
10. **Provider welfare** — payments minus effort, dues, fines, forfeitures, and
    unpaid liabilities.
11. **Expulsion and exit rate**.
12. **Shock recovery time**.

Report member and independent outcomes separately whenever meaningful.

### Round success

`judge_round_result` should be deterministic:

- success when the final signed count equals ground truth and the job completed;
- failure for an incorrect, incomplete, or unavailable job.

This metric represents service success, not covenant stability.

### Operational stability classification

Do not hide the raw outcomes behind a single composite score. A run may be
classified as stable only for summary purposes.

Before full runs, preregister:

- a burn-in window;
- a final evaluation window;
- minimum active member count;
- minimum member compliance rate;
- minimum association-demand rate when association service is available;
- solvency requirement;
- maximum tolerated unpaid liability;
- shock recovery horizon.

A candidate starting definition, subject to research review, is:

- at least two active members;
- no unpaid guaranteed refund and a non-negative bond balance;
- at least 80% member counting and verification compliance in the final window;
- at least 30% association demand when both contract types were available;
- all conditions hold in at least 80% of rounds in the final window;
- after a shock, the run returns to these conditions within eight rounds.

These thresholds are provisional. Finalize them after calibration but before
examining comparative treatment results.

### Institutional stability is not formal Nash equilibrium

The experiment measures dynamic persistence and recovery in stochastic
agent-based simulations. Unless the complete strategy and payoff space is
analyzed separately, describe the result as **dynamic institutional stability**,
not as a formal proof of Nash equilibrium or evolutionary stability.

## 14. Identification and validity safeguards

### Matched comparisons

- Use `seed=42` for the canonical matched comparison.
- Use identical generated cases and audit draws across conditions.
- Keep provider model, system-prompt wording, time budgets, and initial wealth
  constant.
- Change only the intended mechanism.
- Add predeclared robustness seeds after the canonical comparison.
- Run multiple replicas because provider generation remains stochastic even
  when world state is seeded.

### Neutral framing

Avoid morally loaded prompt terms such as "cheat," "honest person," "good
member," or "betray." Describe actions and consequences neutrally:

- inspect versus use available stale information;
- recount versus sign without independent verification;
- guaranteed versus unguaranteed contract;
- rule violation only when referring to the association's explicit terms.

Use "cheating" in analysis labels if useful, but not as a prompt-level demand for
socially desirable behavior.

### Mechanism invariance warning

If C1 through C7 produce nearly identical effort and membership behavior:

- do not conclude that all mechanisms work;
- inspect whether provider prompts prescribe cooperation;
- inspect whether payoffs are actually applied;
- strengthen the strategic calibration;
- test another model family;
- verify that agents understand balances and future consequences.

### Avoid baked-in success

The default parameters must not make either strategy obviously dominant in every
state. The useful region is one where:

- low effort is attractive in the short term;
- membership has meaningful but defeasible future value;
- audits are neither perfect nor irrelevant;
- the premium can cover honest effort under some conditions;
- several violations can materially damage the bond;
- independents remain competitive.

Perform a deterministic payoff-envelope analysis before using LLM runs to tune
behavior.

## 15. Parameter sweeps

The first scientific sweep should vary only the parameters most directly tied to
the theory:

- member price premium;
- detection probability;
- detection lag;
- counting and verification effort cost;
- expulsion permanence;
- shared versus individual liability;
- visibility on versus off.

Use a coarse grid first. Do not launch a full Cartesian product until the coarse
grid identifies a transition region. The desired result is a stability boundary,
not a collection of redundant runs in regions where success or collapse is
automatic.

Hold the canonical judge configuration at
`claude-haiku-4-5-20251001` / `anthropic` if any generic judge-backed language
metrics are run. All economic and institutional metrics should remain
deterministic and event-derived.

## 16. Required scenario knobs

All fields must be required in the Pydantic knobs model; defaults belong in
presets.

### Population and timing

- `provider_count`
- `initial_member_ids`
- `membership_decision_interval`
- `round_count`
- `max_round_duration_seconds`
- `seed`

### Inventory generation

- `true_count_min`
- `true_count_max`
- `stale_count_match_probability`
- `stale_count_max_offset`

### Economics

- `starting_provider_balance`
- `count_effort_cost`
- `verification_effort_cost`
- `independent_contract_fee`
- `association_contract_fee`
- `association_entry_stake`
- `bond_contribution_per_contract`
- `initial_bond_balance`
- `refund_amount`
- `client_incorrect_count_loss`
- `individual_violation_fine`

### Detection and enforcement

- `detection_probability`
- `detection_lag_rounds`
- `expulsion_enabled`
- `expulsion_permanent`
- `reentry_wait_rounds`
- `membership_visible`
- `shared_bond_enabled`

### Client choice

- `client_reliability_window`
- `client_exploration_probability`
- `client_default_expected_error_rate`
- `client_insolvency_penalty`

### Experiment configuration

- `institution_enabled`
- `endogenous_enforcement_enabled`
- inherited `model_overrides`
- inherited `scheduled_events`
- inherited compaction and agent-token settings

Add validators for probability bounds, positive prices and costs, population and
initial-roster consistency, count ranges, non-negative lag, viable contract
staffing, and logically incompatible condition settings.

Knob names may be refined during implementation, but semantics must remain
explicit and presets must be directly comparable.

## 17. Events and auditability

Scenario-specific events should make every outcome reconstructable without
parsing agent prose. At minimum, log typed events equivalent to:

- `bonded_counter_case_started`
- `bonded_counter_membership_changed`
- `bonded_counter_contract_selected`
- `bonded_counter_inspection_performed`
- `bonded_counter_count_submitted`
- `bonded_counter_recount_performed`
- `bonded_counter_signoff_submitted`
- `bonded_counter_job_settled`
- `bonded_counter_audit_scheduled`
- `bonded_counter_audit_resolved`
- `bonded_counter_bond_changed`
- `bonded_counter_member_sanctioned`
- `bonded_counter_member_expelled`
- `bonded_counter_association_insolvent`

Events must include stable agent IDs, round and job IDs, pre/post balances where
applicable, reasons for state transitions, and enough ground truth to recompute
metrics. Private tool results may be present in the event log for research
scoring but must not be broadcast into agent-visible channels.

## 18. GlossoGen implementation shape

Follow `docs/creating-a-scenario.md` and the repository rules in `CLAUDE.md`.

Create:

```text
src/glossogen/scenarios/bonded_counter_association/
├── __init__.py
├── README.md
├── ids.py
├── knobs.py
├── knobs_default.json
├── knobs_no_covenant.json
├── knobs_calibration.json
├── events.py
├── world.py
├── scenario.py
├── mcp_tools.py
├── evaluation/
│   ├── __init__.py
│   └── covenant_stability_metric.py
└── prompts/
    ├── description.jinja
    ├── provider_system.jinja
    ├── provider_injection.jinja
    └── postmortem_injection.jinja
```

Additional presets for ablations may be added after the first three work.

Register `BondedCounterAssociationScenario` in
`src/glossogen/scenario_registry.py`.

### Required platform hooks

- `get_primary_channels`
- `judge_round_result`
- `create_from_config`
- standard world, agent, channel, injection, and MCP-tool hooks
- `restore_state_from_events`, because delayed audits and membership state must
  survive rewind/resume

### Optional hooks worth implementing

- `build_communication_rounds`
- `detect_protocol_boundary_window`
- `get_protocol_explanation_config`

Implement protocol-learning hooks only if provider communication contains a
meaningful institutional norm to transmit. Do not manufacture a language metric
solely because the platform supports it.

### Scenario-specific evaluation

Generic `round_success` is insufficient. Add an event-derived scenario metric
that reports the raw institutional time series and the preregistered stability
classification. It must not use an LLM judge.

Prefer structured measurements for:

- compliance;
- membership;
- demand;
- bond solvency;
- client and provider welfare;
- shock recovery.

If one metric class would produce an opaque overloaded output, use several
specifically named metric classes instead.

### Run-detail extension

A scenario-specific run-detail extension is recommended after core mechanics
work. It should expose, per round:

- true and stale counts;
- contract type;
- primary and verifier;
- hidden effort actions;
- submitted and signed counts;
- audit status;
- membership roster;
- provider balances;
- bond balance and liabilities.

Keep private data out of live agent-visible updates even if it is shown in the
post-run research UI.

## 19. Implementation phases

### Phase 1 — Deterministic economic world

1. Implement knobs and validation.
2. Implement seeded case and audit generation.
3. Implement provider balances, membership, bond, contracts, delayed audits,
   sanctions, and insolvency.
4. Unit-test all state transitions without LLM calls.
5. Verify that matched presets produce identical cases and audit draws.

### Phase 2 — Agent interaction

1. Add provider prompts and role injections.
2. Add costly inspection and recount tools.
3. Add count submission, sign-off, and membership actions.
4. Add early round completion and deterministic failure settlement.
5. Verify that true counts do not leak.

### Phase 3 — Evaluation and visibility

1. Emit reconstructable typed events.
2. Implement deterministic `round_success`.
3. Implement institutional metrics.
4. Add a concise scenario `README.md`.
5. Add the run-detail extension if it does not delay core validation.

### Phase 4 — Smoke tests

1. Run lint and targeted unit tests.
2. Run a three-round calibration smoke test.
3. Run a three-round no-covenant smoke test.
4. Run a three-round full-covenant smoke test.
5. Confirm each JSONL ends with `simulation_ended`.
6. Confirm every completed round has a `RoundResultRecorded`.
7. Confirm institutional metrics are non-empty and match hand calculations.

Do not launch the full experimental grid until the smoke tests pass and the
research framing has been reviewed.

### Phase 5 — Core experiments

1. Run multiple replicas of C0, C1, and C2.
2. Inspect strategic calibration before interpreting C2.
3. Run C3 through C7 as one-mechanism ablations.
4. Identify a coarse stability boundary.
5. Preregister the final stability thresholds and focused sweep.

### Phase 6 — Perturbations and endogenous enforcement

1. Run neutral newcomer replacement.
2. Run opportunist invasion separately.
3. Implement and run costly endogenous enforcement.
4. Test two-sided invasion and institutional genesis only after the established
   institution is understood.

## 20. Tests

At minimum, add deterministic tests for:

- seeded case reproducibility;
- stale count match and non-zero offset behavior;
- private inspection and recount results;
- effort-cost deductions;
- one-call-per-role constraints;
- sign-off without recount;
- correct and incorrect job settlement;
- delayed audit timing;
- detection probability boundary values `0.0` and `1.0`;
- guaranteed refund and bond replenishment;
- bond insolvency and unpaid liability;
- shared versus individual liability;
- expulsion and re-entry rules;
- membership visibility;
- contract availability with insufficient eligible providers;
- scripted client choice from public information only;
- incomplete-round settlement;
- rewind/resume restoration with pending audits;
- deterministic metric reconstruction from events;
- absence of true-count leaks in public messages and injections.

## 21. Kill criteria and redesign triggers

Pause interpretation and revise the design if any of the following occurs:

1. Providers inspect and recount nearly universally in strategic calibration.
2. C1 and C2 produce indistinguishable behavior across adequate replicas.
3. The full covenant always succeeds or always fails across the coarse sweep.
4. Client choice is determined by a hardcoded preference rather than economic
   state and public history.
5. The refund bond is merely decorative and never changes incentives.
6. Expulsion does not remove a valuable future opportunity.
7. Agents receive leaked ground truth or hidden-action information.
8. Too few contract decisions occur to identify a stable pattern.
9. Stability depends on one seed, one replica, or one model family.
10. A composite stability label contradicts its raw component measures.

Negative results are valid. Mechanism invariance, institutional collapse, a
narrow stability region, or inability to transmit norms are substantive
findings when the calibration and measurement checks pass.

## 22. Decisions to confirm with Melanie and Joel

The implementation can begin with the documented defaults, but these research
choices should be explicitly reviewed before full runs:

1. Does this capture the intended meaning of the Covenant Game?
2. Is the primary interest an established institution, institutional genesis,
   or both?
3. Is a shared refund bond central to the theory or only one implementation of a
   member benefit?
4. Should enforcement initially be external, internal, or compared directly?
5. Which stability dimensions matter most: membership, compliance, solvency,
   client trust, invasion resistance, or newcomer transmission?
6. Is permanent identity and expulsion realistic for the intended application,
   or must identity reset be a primary condition?
7. What horizon should count as institutionally stable?
8. Are there canonical payoff assumptions or a formal Covenant Game model from
   Joel that should constrain the parameterization?

## 23. Definition of done for the first implementation

The initial scenario is complete when:

- it is registered and launches through the standard GlossoGen CLI;
- C0, C1, and C2 are represented by validated committed presets;
- cases, audits, economics, membership, sanctions, and delayed consequences are
  deterministic from event data;
- no true-count information leaks to agents without paid effort;
- provider choices affect real balances and future opportunities;
- `round_success` and scenario-specific institutional metrics are deterministic;
- rewind/resume restores membership, balances, bond state, and pending audits;
- targeted tests and repository lint pass;
- three-round smoke runs for C0, C1, and C2 finish with
  `simulation_ended`;
- the scenario README explains mechanics, metrics, scope, and limitations;
- full experiment runs remain pending research review rather than being silently
  launched during implementation.

