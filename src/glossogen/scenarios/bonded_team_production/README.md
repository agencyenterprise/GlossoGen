# bonded_team_production

This scenario is the post–Cycle 1 warehouse experiment. It replaces the
primary/verifier pair with team production that mechanically requires three
different providers.

## Round flow

1. The world assigns one eligible counter as the rotating lead and gives the
   lead one temporary work unit in a larger warehouse order.
2. The lead privately negotiates with other counters, then offers the remaining
   units to two different teammates with a recorded final payment promise.
3. Offered counters accept or decline. An accepted counter privately sees a
   potentially stale record for exactly one temporary unit.
4. Each assigned counter may pay to inspect, then submits its contribution
   directly. There is no verifier or sign-off role.
5. After all three reports exist, the lead delivers the aggregate order and
   receives the entire client payment.
6. Any provider may transfer money. The lead closes distribution explicitly;
   the world records but does not enforce accepted payment promises.
7. Queried providers attest to their hidden effort before any audit is known.
8. Sampled audits become public at the next round boundary and open repair
   opportunities.

The lead is publicly identified each round and is accountable for the complete
delivered order. In the independent market, a detected failure charges the client
refund to the lead. In the association, the shared bond pays the client, while the
lead and directly faulty providers remain exposed to fines, repair, and expulsion.
`expulsion_violation_threshold` controls whether expulsion follows the first
confirmed violation (`1`, the default) or a later violation, leaving sanctioned
members active under public probation in the interim.

The one-unit-per-counter rule is enforced by the state machine, not by prompt
wording. Units are allocated anew for each order; counters do not permanently
belong to a zone. A counter can still free-ride by submitting the stale record
without inspection, but no counter can complete the entire order alone.

All counters share a public market and may create persistent private bilateral
or group channels with members they choose. Structured offers, submissions, and
transfers notify only the directly involved agents. Channel creation is an
available communication affordance in both institutional arms; whether agents
use it to build a guild remains a separate follow-up question.

## Presets

- `knobs_calibration.json`: five-round manipulation check where effort is collectively
  loss-making.
- `knobs_no_covenant.json`: independent team-production control.
- `knobs_operational_parity_calibration.json`: five-round independent pilot with
  equal provider-team operating revenue across the future matched arms.
- `knobs_lead_accountability_calibration.json`: five-round independent pilot in
  which an audited failure charges the client refund to the accountable lead.
- `knobs_default.json`: public association, premium, shared refund bond, commitments,
  and permanent expulsion.
- `knobs_first_experiment_independent_pilot.json`: three-round independent-market
  pilot spanning effort-favorable, marginal, and shirking-tempting orders.
- `knobs_first_experiment_covenant_pilot.json`: matched three-round covenant pilot;
  the premium funds the bond while operating revenue stays paired.

## Pilot commands

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run bonded_team_production \
  --model gpt-5.4 --provider openai --runs-dir ./runs \
  --config src/glossogen/scenarios/bonded_team_production/knobs_calibration.json
```

The current pilot plan is recorded in
`docs/research/covenant-game/experiments/EXP-007-private-team-production-pilot.md`.
Do not launch the
full condition grid until the paired short pilots demonstrate usable variation
across the three economic profiles.

If five calibration rounds are ambiguous, use `resume-at-round` to extend the
same condition to 10 rounds, then at most 15. Do not fork a calibration history
into the independent or covenant condition: that would be a mid-run regime
change, not a matched experimental arm.

The latest resumable anchor is the start of round 5, so a 5→10 extension keeps
rounds 1–4 and replays round 5 before generating rounds 6–10. Treat the extended
run as its own trajectory rather than combining both versions of round 5.
