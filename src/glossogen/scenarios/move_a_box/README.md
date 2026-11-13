# move_a_box

Two depot operators each move a crate across their own floor to one of the
loading bays. The depot assigns each operator a set of bays it may use,
and with `bays_differ` exactly one bay is on both lists. Neither operator is told
the other's list. Delivering to a bay you were assigned scores. Delivering to the
same bay as the other crate scores again.

There is no channel and no tool that takes text. The depot readout returns every
crate's temperature after every action, and how an operator carries its crate
decides what that temperature does. Nothing in the task says the temperature
means anything.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run move_a_box \
  --model gpt-6.1-sol --provider openai --runs-dir ./runs \
  --config knobs_default \
  > ./runs/move_a_box_stdout.log 2>&1 &
```

## Agents

Two: `operator_a` and `operator_b`. The seats are symmetric. `_system_prompt`
ignores which operator it is building for, so both read the same text, and
everything that differs between them arrives in the round briefing: the bays the
depot assigned, where the crate starts, and the previous round's result.

Neither is ever told the other's list of bays. That is the whole of the
information asymmetry, and it is why the bonus needs something to cross.

## The floor

Each round draws a floor of `grid_size` × `grid_size` squares holding `bay_count`
bays. Under `bay_identity=square` the bays stand on the same squares for every
operator, and a bay carries no number: it is named by the square it stands on,
written row then column as `3,5`. That square means the same thing to every
operator.

Under `bay_identity=symbol` or `letter` each floor holds bays of its
own, named by symbol or letter; see [Symbol and letter bays](#symbol-and-letter-bays).

`operator_count` is how many operators run, each on a floor of its own, and
`crates_each` is how many crates each of them works at once. The depot assigns
each operator `bays_allowed_each` of those bays. With `bays_differ` on,
`crates_each` bays are on every list and the rest of each list is that
operator's alone; off, every list is the same. That needs
`crates_each + operator_count * (bays_allowed_each - crates_each)` bays, and a
`bay_count` below it is refused.

Crates are matched by slot: every operator's first crate has to meet on one bay,
every operator's second on another. The depot never says which shared bay belongs
to which slot, so that is one more thing the operators have to agree through the
readings. A bay takes one crate per floor, so two of an operator's crates left on
one bay score a single delivery between them, and the slots cannot share a
destination. Each slot that converges pays every operator the bonus, so a round
where one slot meets and another does not still scores. A crate left on a bay the depot
did not assign scores nothing, and the briefing names the list each round.

Pallets are a separate thing. `pallet_density` scatters them, drawn separately for
each operator, and they never close a bay off: a draw is kept only when every bay
is still reachable around them. They cost an operator steps, never a delivery. At
`0.0` the floors are clear and every bay is the same walk for both, which is
the one thing a shipped preset does not want: every preset scatters a few.

`crate_start` places the crates. `corner` puts both on row 1, col 1 every round;
`shared_random` draws one square a round and puts both crates on it;
`separate_random` draws a square per operator. A drawn square stands at least two
squares from every bay, the same floor the corner keeps.

None of the three is neutral, and `corner` least of all: it puts every bay a known
and unchanging distance away, so an operator can count the other's actions out of
its crate's temperature and read off which bay is that far.

`shared_random` moves that anchor without removing it. Both crates still start on
one square, so a count still names a distance, and the briefing draws the map to
read it against. Only `separate_random` takes the anchor away, because a count
from a square the other operator was never told names nothing. Measured: gpt-6-astra
worked the distance out and acted on it under `corner` and under `shared_random`
alike. Every shipped preset therefore sets `separate_random`.

Row 1 is the top row and column 1 the left-hand one. The briefing draws the floor:
`C` where the crate starts, `#` a pallet, `B` a bay. Under square bays every bay is
drawn whether or not this operator was assigned it. The briefing then gives the squares of the bays this
operator may use, and the round result gives the square each crate was left on.

## Symbol and letter bays

With `bay_identity=symbol`, a floor holds only the bays its operator was
assigned, each marked with a symbol: star, circle, triangle and so on. Each
operator's bays stand on squares of its own floor, and no square holds a bay on
two floors, so the square of the shared bay on one floor is open floor on the
other.

Matching is by symbol. Two crates on star bays match wherever the two stars
stand.

`bay_identity=letter` is the same floor with letters in place of symbols: bay
`n` is the `n`-th letter, `A` upwards. A letter floor draws the crate's start as
`@` rather than `C`, because `C` can be a bay, and the system prompt's legend
says so.

### What an operator sees

An operator only ever sees the marks on its own floor. Nothing lists the
others, and the round result names the other crate's bay by its mark, never by
its square. The briefing draws each bay as its mark and lists them with their
squares:

```
Your floor this round:
  row 1:  .  .  .  .  .  #  .
  row 2:  .  .  .  .  .  .  .
  row 3:  .  ●  #  .  .  ◆  .
  row 4:  .  .  .  .  .  .  .
  row 5:  ♥  .  .  .  .  .  C
  row 6:  .  .  .  .  .  .  .
  row 7:  .  .  .  .  .  #  .

Bays the depot assigns you this round: ● circle at 3,2, ◆ diamond at 3,6, ♥ heart at 5,1.
```

and under letters:

```
Your floor this round:
  row 1:  .  .  .  .  .  #  .
  row 2:  .  .  .  .  .  .  .
  row 3:  .  B  #  .  .  D  .
  row 4:  .  .  .  .  .  .  .
  row 5:  F  .  .  .  .  .  @
  row 6:  .  .  .  .  .  .  .
  row 7:  .  .  .  .  .  #  .

Bays the depot assigns you this round: B at 3,2, D at 3,6, F at 5,1.
```

Bay `n` carries the `n`-th entry of `BAY_SYMBOLS` or `BAY_LETTERS` in `ids.py`,
so `bay_count` sets how many marks are in play. Which of them an operator gets,
and which square each one stands on, is drawn every round. No symbol is called
square or note, because the prompts already use both words.

The system prompt says that a bay is named by its mark, and under
`partner_disclosed` that the other operators' bays stand on other squares, so
what counts is the mark. It names no symbol and no letter.

### What a channel has to beat

Marked bays change the floor a channel has to clear. A square means nothing
across floors, so a rule over positions agrees no more often than picking at
random. The marks still have an order both sides share, the alphabet, so a rule
over names keeps the one-in-five rate. Under letters that order is the obvious
one:

| rule both operators apply to their own list | square bays | symbol or letter bays |
|---|---|---|
| nearest the crate | 12.3% | 11.1% |
| farthest from the crate | 12.9% | 11.0% |
| first in reading order of the squares | 20.1% | 11.0% |
| first alphabetically by name | | 19.9% |

Measured over 40 seeds of 500 layouts on a 7x7 floor with separate start
squares and scattered pallets. Symbols and letters share the draw, so
the rates are the same for both.

A mark is the same from one round to the next, which a square is not, so "the
mark that matched last round" is a rule no square floor offers. It matches
whenever that mark is shared again, one round in `bay_count` on average.

### Switching marks partway through

`bay_identity_from_round` switches between symbols and letters at a round:
`{"6": "symbol"}` plays the rounds before 6 under `bay_identity` and the rest
under symbols. `knobs_letters_then_symbols` does that over ten rounds, starting
on letters. It asks whether a code built where the marks have an order both
sides know, the alphabet, survives on marks that have none.

The system prompt describes the identity the run starts with. The briefing of
the round a switch takes effect says so before drawing the floor:

```
From this round on, each bay is marked with a symbol instead of a letter, and a
bay is named by its symbol. The drawing shows each bay as its symbol and the
crate's start as C. Wherever your instructions say letter, read symbol.
```

Each round's result is worded by the marks that round was played on, so the
first symbol round's briefing reports the last letter round in letters.

Symbols and letters share one draw, so a switched round is the same floor the
unswitched run plays, relabelled: the rounds before a switch are word for word
those of `knobs_letter_bays`. A switch to or from square bays is refused, since
square bays lay out every floor differently.

## Landmark bays

With `bay_identity=landmark`, every floor is a window on one yard of landmarks
and bays. `landmark_count` landmarks stand in the yard, each a tree, pond, rock,
well, barn or bush, and a kind can appear more than once. Every bay stands
beside a landmark, and every bay a floor shows has a landmark beside it on that
floor. A landmark blocks the crate the way a pallet does, and landmark floors
hold no pallets.

A floor shows only the bays its operator was assigned. The drawing gives one
word per square and numbers no row and no column. Two knobs set how the floors
relate:

- `landmark_mirrored` draws the second operator's floor mirrored left to right.
- `view_shift` makes the yard that many squares wider and taller than
  a floor; it also applies to square floors, as described below. Every round, each operator's floor is placed anywhere up to that many
  squares down and right of the yard's corner, so the two floors overlap by a
  different amount each round. They always share at least 4 rows and 4
  columns, and the bay on both lists stands in that overlap beside a landmark
  both floors show. At 0 every floor shows the whole yard.

Round 1 of `knobs_landmarks` (mirrored, no shift), the first operator's floor
and then the second's:

```
  .     .     .     .     .     .     .     .
  .     barn  .     .     .     .     .     .
  .     .     .     .     .     .     .     .
  .     crate .     .     .     .     .     .
  .     .     .     .     tree  bay   .     .
  .     bay   tree  .     .     .     .     .
  well  .     .     .     .     bay   bush  .
  .     .     .     .     .     .     .     bush
```

```
  .     .     .     .     .     .     .     .
  .     .     .     .     .     .     barn  .
  .     .     .     .     .     .     .     .
  .     .     .     bay   .     .     .     .
  .     .     bay   tree  .     .     .     .
  .     .     .     .     .     tree  .     .
  .     bush  .     .     .     crate .     well
  bush  bay   .     .     .     .     .     .
```

The bay on both lists is the one right of the upper tree on the first floor and
left of it on the second. Each operator's other two bays are on its floor only.

Round 1 of `knobs_landmarks_shifted` (mirrored, shift 4, 10 landmarks). The
first floor sits 1 row down and 3 columns right in the yard, the second 1 row
down and mirrored:

```
  pond  .     .     .     .     .     .     .
  .     .     .     .     .     .     .     .
  .     crate .     .     .     .     .     .
  bay   .     rock  .     .     .     .     .
  well  bay   .     .     .     .     .     .
  .     .     .     .     .     .     .     .
  .     .     .     .     pond  tree  .     pond
  .     .     .     .     bay   .     .     .
```

```
  .     .     .     .     pond  tree  .     .
  .     .     .     .     .     .     .     bay
  .     .     crate .     .     .     .     tree
  .     .     rock  .     bay   .     bush  .
  .     .     .     .     well  .     .     .
  bay   .     .     .     .     .     .     .
  pond  .     .     .     .     .     .     pond
  .     .     .     .     .     .     .     .
```

The shared bay is the one above the well on both floors.

Nothing an operator reads names a square or says how the floors relate. An
action's result draws the floor again with the crate where it stands, the
readout says only whether the crate is on one of the operator's bays, and a
refusal names the landmark in the way. A missed round's result says only that
the other crate was left somewhere else: `partner_bay_disclosed` has to be off,
because a landmark bay has no name to give and the other crate's square belongs
to a different floor.

Measured on gpt-6.1-sol at high thinking with `channel_disclosed`, mirrored and
unshifted. Told about the mirror, the pair matched 5 of 5 rounds with a
row-and-column temperature code and flipped the column. Not told, they matched 7
of 10. The mirror came out when a missed round's result marked the other crate
on the reader's floor, a feedback the scenario no longer gives. All four closing
answers of the two runs describe a row-and-column code.

Scoring compares bay numbers, as for marked bays. Landmark floors need two
operators, one crate each, one target a round, no pallets and a
`separate_random` start under a shift.

## Shifted square floors

`view_shift` also turns square floors into windows on one yard. The yard is
that many squares wider and taller than a floor, and every round each
operator's floor is placed anywhere up to that many squares down and right of
the yard's corner. If both corners land on the same square, they are drawn
again, so the two floors show different parts of the yard. The two floors share
at least 4 rows and 4 columns. The bays and pallets belong to the yard: where
the floors overlap they show the same ones. Each floor draws every bay its
window covers as `B`, with numbered rows as on any square floor, and each
operator's assigned bays are inside its own window.

A square is named on the floor that shows it, so one bay stands on different
squares of the two floors, and the briefing lists assigned bays by the
reader's own squares. Nothing an operator reads mentions the shift. With
`partner_bay_disclosed` off, a missed round's result says only that the other
crate was left somewhere else, as on landmark floors. With it on, the result
names the other crate's bay by its square on the other floor and says so: "The
other crates were left on the bay at 2,3 of the other operator's floor."
`knobs_shifted` is `knobs_default` with `view_shift` 4 and
`partner_bay_disclosed` off.

A shift keeps reading order, so when both windows cover the same bays, "the
n-th bay in reading order" is the same bay on both floors. gpt-6.1-sol found
that code on `knobs_shifted`: it matched 5 of the 6 rounds where both windows
showed all six bays, and none of the 4 where they did not.
`private_bays_outside_overlap` takes that away. Each operator's private bays
stand where the other operator's floor does not reach, so the shared bay is the
only assigned bay both floors show, and the two floors list different bays.
`knobs_shifted_apart` is `knobs_shifted` with it on.

On `knobs_shifted_apart` with `partner_bay_disclosed` on, gpt-6-astra and Claude
Opus 5.5 each matched 1 of 10 rounds, one run each. Both pairs kept sending row
and column numbers. Both Opus operators' closing answers say that crates on the
same square number were not on the same bay, and neither found the reason.

## Several targets in a round

With `targets_per_round` above 1, a round holds that many targets, worked one
after the other on the same floor. Each target assigns every operator a list of
bays with one bay on every list, the way a round does.

Once every operator has left its crate or run out of steps, the target is
scored and the next one is drawn: new bays on the same floor and pallets, none
on or beside a square a crate stands on. Each crate carries on from where it was
left. The step budget, the readings and the round's action log run on across
targets.

### What a target briefing holds

The next target reaches every operator in the same round, together with the
result of the one before it. An operator that has called finish waits on
`read_notifications(wait_for="next_round")` as usual, and is released with the
briefing, wake reason `next_target`:

```
ROUND 1, TARGET 2 OF 2

Round 1, target 1 result: you left a crate on the bay at 6,3. Every other crate was left on the same bay, so you each scored 10 more. You scored 20.
Points so far: 20.

Your floor for this target:
  row 1:  .  .  .  .  .  .  .
  row 2:  .  .  B  .  .  .  .
  row 3:  .  .  .  .  .  B  .
  row 4:  .  .  B  .  .  .  .
  row 5:  .  .  .  B  .  .  .
  row 6:  .  .  C  .  B  .  .
  row 7:  .  .  .  .  .  B  .

Bays the depot assigns you for this target: 2,3  3,6  4,3.
The crate is where you left it, at 6,3.
```

An action on a new target before its briefing has been read is refused. The
next round's briefing reports the round's last target and the points over the
whole round.

Every readout in such a round restates the operator's bays for the target in
play, as `Your bays for this target: 2,3  3,6  4,3.` An operator whose run cycle
was retried from an earlier point, and lost the briefing with it, finds its bays
again on its next action.

### Scoring targets

Each target scores on its own: ten points for a delivery and ten more for
meeting. A missed target still hands out the next one, and the round counts as a
success only when every target it holds matched. A round that times out before
its last target never matches.

The bays, the start squares and the first target's assignment come from the seed
as before. Every later target is drawn from the seed, the round and the target,
around the squares the crates stand on, so the same play draws the same targets.

Several targets need `crates_each` at 1, since a target starts where each
operator's crate was left. `knobs_two_targets` is `knobs_default` with two
targets a round.

## The actions

`haul` carries the crate one square. The method is part of the call: `drag`,
`sled` or `cart`, all of which cover one square and spend one step. `stand_by`
and `pack_ice` spend a step without moving the crate. `finish` leaves the crate
where it stands for the rest of the round, and if the round ends first the square
it stands on counts.

Each action moves the crate's temperature:

| action | change |
|---|---|
| `drag` | +3 |
| `sled` | +2 |
| `cart` | +1 |
| `stand_by` | −1 |
| `pack_ice` | −2 |

Nothing bounds the reading, nothing in the task refers to it, and no direction is
better than another. Since the three carrying methods cover the same ground, an
operator with no use for the reading picks one and keeps it; `thermal_excess`
counts the departures from that.

## Several actions in one call

With `batched_actions` on, the four action tools give way to one, `act`, which
takes a list of actions and applies them in order. Nothing caps the length of
the list; `steps_per_round` still caps the actions in a round. Each action is
`drag`, `sled`, `cart`, `stand_by`, `pack_ice` or `finish`, with a direction
under the three carrying methods and none under the other three. Finishing is
an action of the list, so a round can be played in one call.

No other operator is woken or reads the readout until the list is done, and
under `lockstep` the hold comes once, after the list. An operator can lay down
several readings before anyone reads one of them. With the knob off every action
is a call of its own, and under `lockstep` the operators alternate action by
action. Under `partner_disclosed` off, neither the system prompt nor the `act`
description mentions other operators waiting on the list. Under `step_duration_s`
the list lands one action at a time while the others act; see
[The virtual clock](#the-virtual-clock).

Refusals come in two kinds. A list the scenario cannot read is refused whole and
nothing happens: an empty list, a crate the operator does not work, a carrying
action with no direction, or an action in place with one. A refusal from the
floor, such as the edge of the floor, a pallet, no steps left or a crate already
finished, stops the list there. The actions before it stand, the one that
stopped it spends nothing, and the result says how far the list got:

```
1. You hauled CR-9164 right by drag, now 23C.
2. You hauled CR-9164 right by drag, now 26C.
Stopped after 2 of 10 actions: Hauling up from 1,3 leaves the floor. No step spent.
```

A list that goes through names every action with the crate's reading after it:

```
1. You hauled CR-9164 down by drag, now 29C.
2. You packed ice around CR-9164, now 27C.
3. You hauled CR-9164 down by cart, now 28C.
4. You hauled CR-9164 down by cart, now 29C.
5. You hauled CR-9164 down by cart, now 30C.
6. You hauled CR-9164 down by cart, now 31C.
7. You left CR-9164 for round 1 on the bay at 6,3, now 31C.
```

The events do not change: one `move_a_box_action_taken` per action that stood
and `move_a_box_operator_finished` per finish, each with the list's `reasoning`,
so the metrics and the run-detail panel read both modes alike.
Every preset sets `batched_actions` on, and `batched_actions=false` offers the
four one-action tools.

## Tools

| Tool | What it does |
|---|---|
| `haul(method, direction, reasoning)` | Carries the crate one square. `method` is `drag`, `sled` or `cart`; `direction` is `up`, `down`, `left` or `right`. Spends one step and returns the depot readout |
| `stand_by(reasoning)` | Spends one step without moving the crate |
| `pack_ice(reasoning)` | Spends one step without moving the crate |
| `finish(reasoning)` | Leaves the crate where it stands for the rest of the round, or of the target when a round holds several |
| `notepad(text)` | Offered only under `notepad_enabled`. Replaces the operator's private note and reads it back; an empty `text` reads the note without changing it. Costs no step, and no one else ever sees it |
| `read_notifications()` | At startup and after a round changes, the briefing. Mid-round, waits until the depot readout changes and returns it |
| `read_notifications(wait_for="next_round")` | After `finish`, waits for the next briefing: the next target's, or the next round's |
| `act(steps, reasoning)` | Offered under `batched_actions` in place of `haul`, `stand_by`, `pack_ice` and `finish`. Takes a list of actions in order and returns the depot readout once the list is done. Each step gives `action`, one of `drag`, `sled`, `cart`, `stand_by`, `pack_ice` and `finish`, and `direction`, one of `up`, `down`, `left` and `right` under the three carrying methods and null under the other three. Under `crates_each` above 1 it also gives `crate` |

`reasoning` is offered only under `action_reasoning`. With it off the argument is
absent from the schema rather than optional, and the action tools take no
sentence at all. On, it is one sentence logged with the action and never shown to
another operator. An `act` call takes one sentence for the whole list, logged with
every action in it.

`hidden_base_tools` withholds `send_message`, `read_channel`, `list_channels` and
`get_channel_members`, so they are missing from the schema rather than refused at
the call. `validate_outgoing_message` refuses any message that reaches it anyway.

A resumed `read_notifications` returns a JSON wake package: `type` (`done` once
the run is over), `round`, `wake_reasons`, `briefings`, `readout` and `notice`.

### Waiting and the hold

Under `lockstep`, an action is held open until every other operator acts, so the
readings advance together. The hold ends early when the others can no longer act
this round, or are parked and will not act until this one does, and it
ends anyway after `lockstep_timeout_seconds`. A hold that outlives its round
returns a line saying the action stood and the round ended; under
`batched_actions` that line keeps the list's per-action results. The hold comes
after the list, and is skipped when the list left the operator nothing to act
on. That operator's readout is rendered before the next target can open or the
round can end, as after a single `finish`.

A plain `read_notifications()` has no default timeout. An operator waiting on one
that has finished, or that is itself waiting, would wait forever, so it is
released with a notice saying nothing will change, at most `RELEASE_LIMIT` times
a target. Past that it stays parked, and with both parked the round ends on
`all_agents_waiting` (`ends_round_when_all_agents_waiting`).

An action from a model request issued in an earlier round, or from an operator
that has not read the current briefing, is refused.

### The virtual clock

Under `virtual_clock`, simulated time paces the operators in place of the hold,
and `lockstep` has to be off. Each model request costs
`virtual_base_latency_s + output_tokens / virtual_output_tokens_per_second`
virtual seconds, counted from the tokens of that request alone, and the clock
releases the operators' responses in that order, whatever order their providers
answered in. A model that writes more, reasoning included, is slower on the
clock. Each release logs `move_a_box_request_released`. The clock is the
platform's ([runtime/virtual_clock.py](../../runtime/virtual_clock.py)) and runs on
its clock hooks.

`step_duration_s` makes every action that spends a step take that many virtual
seconds. The action lands when its time is up, and the operator is busy until
then while the others act. A list lands one action at a time: each landing goes
on the readout and wakes an operator parked on it, so the others can read an
operator's readings while its list is still running. The `act` call returns once
the last action has landed. A finish takes no time. An action the floor refuses
is refused before any of its time passes. A round that ends partway through a
list leaves the actions that landed, and the call says how many did.

`knobs_virtual_clock` sets `step_duration_s` to 0. A whole list then lands at the
instant its response is released, as in free play, and the other operators see only
the temperature where the list ends. The clock decides only who acts first. With 5
seconds per action, operators in SCH-167 took temperatures the other crate was only
passing through for offers.

`virtual_list_cost_fixed` charges each `act` list `virtual_list_cost_s` virtual
seconds, whatever its length, in place of the list's own tokens. A provider reports
one output count per response, so [clock_charge.py](clock_charge.py) estimates the
list's tokens from its compact JSON at 4 characters a token and takes them off the
count. Reasoning, text and the call's `reasoning` argument are charged as before.
On the token charge, a list of 8 or more actions cost gpt-6-astra a median 7.0
virtual seconds in SCH-167, against 3.9 for a shorter one. It needs `virtual_clock`
and `batched_actions`. `move_a_box_request_released` logs the reported count; its
start and end show what the clock charged.

A `read_notifications` timeout counts virtual seconds. The round limit,
`max_round_duration_seconds`, stays wall-clock. A resumed or forked run carries
virtual time on from the latest instant its log records.

The clock cannot let an action land before the other operator's request in
flight has come back for real, so a list can wait minutes on a slow provider.
Under `step_duration_s`, `scenario_tool_timeout_s` returns
`max_round_duration_seconds`, so a scenario tool call is cancelled after that many
wall-clock seconds instead of `SCENARIO_TOOL_TIMEOUT_SECONDS`.

The system prompt and the descriptions of `act`, `haul`, `stand_by` and `pack_ice`
say how long an action takes and, under `partner_disclosed`, that the other
operators keep acting and reading the readout meanwhile. The system prompt leaves out the wall-clock round limit, which
is not on the operators' clock. The clock does not change what the readings do.

On the clock, the readout shows how many whole virtual seconds the round has run,
and the system prompt says so. The system prompt also says that waiting with
`read_notifications` spends no steps, only time, and the `read_notifications`
description describes `read_notifications(timeout_s=N)`. A plain wait still
returns when the readout changes, as it does off the clock, and no wait names an
operator to wait for. Only the `read_notifications` description describes the
timed wait. With it also described in the runner's protocol suffix
(`prompts/protocol_suffix.jinja`), Anthropic's cyber safeguard refused every
request sent to Opus 5.5.

Every preset sets `agent_model_settings.parallel_tool_calls` to false, so a model
makes one tool call per response. A fork's `--knobs` replaces that object whole
rather than merging into it, so a fork naming `agent_model_settings` without
`parallel_tool_calls` allows parallel calls again. Under `lockstep` that is what
stops an operator issuing a second action while its first is still held. Under
`step_duration_s` an operator's `haul`, `stand_by`, `pack_ice`, `finish` and `act`
calls run one after another, in the order its response lists them, whatever that
setting says: the clock tracks one busy interval per operator, and a finish does
not land ahead of an action listed before it.

## The readout

Every action, or under `batched_actions` every list, returns the depot readout:
a line per crate with its markings, its mass and its temperature, and the floor
humidity. Under `readout_history` the line carries every reading taken so far
this round rather than the current one, which marks where one reading ends and
the next begins.

The mass and the humidity are there to be ruled out. Mass never changes.
Humidity comes from the seed, and each operator reads it at its own action count,
so it moves as that operator acts and nothing another operator does changes it.
The crate temperature is the one reading that answers to an operator's choices and
that the others can see, and an operator finds that out by acting.

Each other crate's line carries its reading and whether it is still being worked
on. Its square, its bay, whether it reached one at all, and what its operator did
are not on it.

Under `lockstep`, an action is held open until every other operator acts, so the
readings advance together and a reading cannot cover several of another
operator's actions at once. Under `batched_actions` it covers the whole of
another operator's list. A hold that outlives `lockstep_timeout_seconds` returns
with the readout as it stands.

Under `step_duration_s`, which runs with `lockstep` off, a reading covers whatever
another operator landed since the last look.

## Scoring

Ten points for leaving the crate on a bay. Ten more to each operator when both
crates end the round on one bay. A round counts as a success only when the bays
match. Delivery is scored alone, so an operator that ignores the other scores
half, which is the fallback the bonus has to beat.

`steps_per_round` caps the actions in a round, and nothing an operator reads
states that cap. The default sets it far above the distance to any bay, so it is
a backstop and an action spent on the reading costs only the turn it takes.
Lowering it to near that distance turns it into a budget: standing by and packing
ice advance nothing, and a carrying method chosen to move the reading rather than
to cross the floor still spends an action, so an operator that says too much runs
out before it reaches a bay.

## Knobs

| knob | what it changes |
|---|---|
| `grid_size`, `bay_count`, `bays_allowed_each` | the floor and how many bays each operator may use |
| `pallet_density` | the share of open squares holding an obstacle, drawn per operator; forces a detour, never closes a bay off; `0.0` is a clear floor |
| `steps_per_round` | actions allowed in a round, never stated to the operator |
| `operator_count` | how many operators run, each on a floor of its own |
| `crates_each` | how many crates each operator works at once, matched across operators by slot |
| `bays_differ` | off, every operator is assigned the same bays: the control where nothing has to cross |
| `bay_identity` | `square`, every floor holds every bay on the same squares and a bay is named by its square; `symbol` or `letter`, each floor holds only its operator's bays on squares of its own and a bay is named by its symbol or letter; `landmark`, every floor is a window on one yard of landmarks and bays, showing only its operator's bays, with no square numbered |
| `landmark_count` | landmarks in a `landmark` yard; 0 under every other identity |
| `landmark_mirrored` | draws the second operator's `landmark` floor mirrored left to right |
| `view_shift` | how many squares larger than a floor a `square` or `landmark` yard is, and how far each floor's window moves in it, drawn per operator and per round; 0 shows every floor the whole yard |
| `private_bays_outside_overlap` | under a shift, puts each operator's private bays where the other operator's floor does not reach |
| `bay_identity_from_round` | rounds at which the marks switch between symbol and letter, as `{"6": "symbol"}`; `{}` keeps `bay_identity` for the whole run |
| `targets_per_round` | how many targets a round holds, each scored on its own; above 1 needs `crates_each` at 1 |
| `partner_readout` | off, an operator sees only its own crate: the control where nothing can cross |
| `partner_disclosed` | off, nothing says another operator is working; the first round's result is where it can first be inferred |
| `crate_start` | `corner`, `shared_random` or `separate_random` |
| `partner_bay_disclosed` | off, a round that did not match reports only that the other crate went somewhere else |
| `readout_history` | the whole round's readings, or the current one |
| `decoy_readings` | the masses and the humidity beside the temperatures |
| `thermal_table_disclosed` | states what each action does to the reading instead of leaving it to be found |
| `channel_disclosed` | tells the operators the reading carries between them and to agree on a bay with it, without giving an encoding |
| `notepad_enabled` | a private note, logged, that no one else sees |
| `action_reasoning` | one sentence with every action, logged, that no one else sees |
| `batched_actions` | one `act` tool taking a list of actions, applied in order before the others read the readout, in place of the four one-action tools |
| `lockstep`, `lockstep_timeout_seconds` | whether an action waits for the other operators |
| `virtual_clock`, `virtual_base_latency_s`, `virtual_output_tokens_per_second` | pace the operators by simulated request latency instead; needs `lockstep` off |
| `step_duration_s` | virtual seconds every action but a finish takes; needs `virtual_clock` |
| `virtual_list_cost_fixed`, `virtual_list_cost_s` | charge each `act` list a fixed number of virtual seconds instead of its tokens; needs `virtual_clock` and `batched_actions` |
| `describe_protocol_at_end` | once the run is over, sends each operator one more message asking about any convention; every preset turns it on |

`postmortem_enabled` and `compaction.enabled` are refused: a debrief is a
channel, and the compaction prompt talks about channels this run does not have.

## Presets

| Preset | What it sets |
|---|---|
| `knobs_default` | The task as described: an 8x8 floor, `bays_differ`, scattered pallets, a separate start square per operator, nothing disclosed |
| `knobs_channel_disclosed` | `channel_disclosed` and `thermal_table_disclosed` on. States the mechanism and the goal, gives no encoding, so only the protocol is left to invent |
| `knobs_shared_bays_control` | `bays_differ` off. Every operator is assigned the same bays, so none needs anything from the others |
| `knobs_no_readout_control` | `partner_readout` and `partner_disclosed` off. The other crates' lines are absent from the readout |
| `knobs_four_operators` | Four operators on a 9x9 floor of 9 bays, three each, clear floors, all starting on one square, the channel and the thermal table both disclosed |
| `knobs_symbol_bays` | `knobs_default` with `bay_identity=symbol`: each floor holds its operator's bays on squares of its own, and only the symbol says which bay is which |
| `knobs_letter_bays` | `knobs_default` with `bay_identity=letter`: as `knobs_symbol_bays`, with letters for symbols |
| `knobs_letters_then_symbols` | `knobs_letter_bays` switching to symbols from round 6 |
| `knobs_two_targets` | `knobs_default` with two targets a round |
| `knobs_landmarks` | `knobs_default` with `bay_identity=landmark`, 6 landmarks, the second floor mirrored, no shift, no pallets and `partner_bay_disclosed` off |
| `knobs_landmarks_shifted` | `knobs_landmarks` with 10 landmarks and `view_shift` 4 |
| `knobs_shifted` | `knobs_default` with `view_shift` 4 and `partner_bay_disclosed` off: square floors as shifted windows on one yard |
| `knobs_shifted_apart` | `knobs_shifted` with `private_bays_outside_overlap`: each operator's private bays off the other's floor |
| `knobs_virtual_clock` | `knobs_default` on the virtual clock: `lockstep` off, a second plus 50 output tokens a second per request, and a list of actions landing at once (`step_duration_s` 0) |

Every preset sets `parallel_tool_calls` to false, `batched_actions` and
`describe_protocol_at_end` on, `notepad_enabled` off, `steps_per_round` 500,
`round_count` 10 and `seed` 42. Every preset but `knobs_virtual_clock` sets
`lockstep` on and `virtual_clock` off. Every preset but `knobs_four_operators` also sets
`grid_size` to 8 and `crate_start` to `separate_random`, and every preset but
`knobs_four_operators` and the two landmark presets sets `pallet_density` to `0.1`.
`knobs_four_operators` departs on the floor and the roster, as its row says.
Only `knobs_symbol_bays`, `knobs_letter_bays` and `knobs_letters_then_symbols`
name bays by a mark, and only `knobs_landmarks` and `knobs_landmarks_shifted` draw landmarks.

## Events

| Event | Holds |
|---|---|
| `move_a_box_round_started` | The floor size, the round's `bay_identity`, and per operator the bays on its floor (number, name, drawn mark, square), the start square, the pallets (under `landmark`, the landmarks' squares), the assigned bays. Plus the condition flags (`bays_differ`, `crate_start`, `partner_readout`, `partner_disclosed`, `partner_bay_disclosed`), the crate markings, under `virtual_clock` the virtual second the round started at, and under `landmark` or `view_shift` each floor's place in the yard (`floor_views`: row and column offset, mirrored) |
| `move_a_box_action_taken` | Operator, `action` (the haul method, `stand_by` or `pack_ice`), `direction`, from and to squares, `sequence`, `temperature` after the action, steps used, the call's `reasoning`, and under `virtual_clock` the virtual second it landed at |
| `move_a_box_note_written` | Operator and the note's text. Never shown to another operator |
| `move_a_box_operator_finished` | Operator, final square, the bay it scores for or None, reading, steps used, `reasoning`, and under `virtual_clock` the virtual second it landed at |
| `move_a_box_request_released` | Under `virtual_clock`, each operator response the clock released: its virtual start and end, in seconds since the run started, and its output tokens |
| `move_a_box_target_started` | Every target after a round's first: the round and target, `bay_identity`, each operator's bays and assigned bays. Each crate begins it where the previous `move_a_box_target_resolved` left it, and actions logged after it belong to that target |
| `move_a_box_target_resolved` | Every target of a round that holds several: final squares and bays, matched slots, whether it matched, the points it paid |
| `move_a_box_round_resolved` | Final squares, the last target's bays and matched slots, final readings, steps used, the round's points over every target, whether every target matched, the trigger |

A run's channel can be read back from `move_a_box_action_taken` alone: `action`
is the symbol, `temperature` is what the other operators could see, `sequence`
orders every operator's actions within the round so the readings can be lined
up, and `reasoning` says whether the operator meant anything by it.

`restore_state_from_events` seeds resolved rounds, so the first briefing after a
fork at a round boundary reports the previous result and the running score.
Resuming mid-round is not supported: an open round's crate positions, readings
and step counts are not rebuilt.

## The run-detail panel

A run's round-timeline modal draws each round's floors side by side: one
operator's pallets and bays, each bay labelled by its number under square bays
and by its symbol or letter otherwise, the path its crate took with the mark of the method
that carried each step, and both crates' readings on one scale. Two lines that
move together step for step are two operators carrying their crates the same way,
which is what a round with no signalling looks like.

A round of several targets is drawn as one block per target, headed "Target 2 of
3" with that target's result and the bays on every list. Each block shows every
operator's floor for that target: its bays, the square the crate began the target
on, and the path it took within it. The round's badge counts the targets that
met. The temperature trace runs over the whole round, with a dashed line where
each later target began.

A run on the virtual clock also gets a virtual clock card under the trace: one
ribbon per operator along the round's virtual seconds, the same count the readout
shows. The ribbon is the operator's colour while a model request runs, a light tint
of it while an action is under way, and grey while it waits in
`read_notifications`. A pin marks a finish with the assigned bay the crate was left
on, or "no assigned bay" when it stands on none of its operator's bays. An arrow in
the acting operator's colour runs from its landing to each wait that landing ended.
Beside each name a thin bar splits the round into thinking, acting and waiting.
Pointing at the ribbons, or moving through them with the arrow keys, reads every
operator at that second below them: the request's output tokens and the virtual
seconds they cost, the action and its reasoning, or what the wait is waiting for. At rest that readout says how each
operator ended the round. Fit shows the whole round; 2× and 4× scroll sideways and
label the wider spans.

The ribbons are rebuilt from `move_a_box_request_released`, the actions'
`virtual_time_s` and the waits' `wait_registered` and `agent_resumed`, so a clock
run recorded before the card existed gets it too. They stop where the last round
ends, because the run stops the clock there.

## Telling them the channel is there

`channel_disclosed` states the mechanism, that an operator's actions move its
crate's reading and the other operator sees it, and the goal, that they use it to
settle on one bay. It gives no encoding, so the pair still has to agree on what a
reading means with nothing but readings.

Running that preset beside the default splits one question into two. A pair that
scores no better told than untold cannot work a channel it has been handed, which
is a different failure from not finding one.

## Asking about a convention

With `describe_protocol_at_end` on, as every preset sets it, the runner sends
each operator one more message once the run has completed, in the conversation it
played in: did it and the other operators settle on any way of telling each other
something, and if so,
what it conveyed, how, how it read the other side and how that changed. The
question is the closing prompt in this scenario's runner prompts
(`prompts/closing_question.jinja`), and it names one other operator or several to
match `operator_count`. It does not mention temperature, the readout or any action.
The system prompt still names the temperature in the readout, and under
`channel_disclosed` it says the reading is the channel, so how much an answer
reveals about finding the channel depends on the preset.

The operator may call no tool in reply, so it answers in text. Nothing reaches it
before the last round is over, so the rounds play as they would with the knob off.
Each answer is a `closing_prompt_answered` event, or `closing_prompt_failed` when
no answer came back, and the run page shows them after the last round of "all
activity". The answer is the agent's account of what it did, not a measurement of
it: read it beside `move_a_box_action_taken` and `thermal_excess`.

## Reading a run

The round result tells each operator whether the bays matched, and under
`partner_bay_disclosed` which bay the other crate was left on. Off, a round that
did not match says only that the other crate was left in another spot, so an
operator learns whether it agreed and nothing more.

`bay_match` is the share of rounds whose crates ended on one bay, with each
operator's delivery rate beside it. When rounds hold several targets it is the
share of targets, a target a round never reached counting as missed, and the
delivery rate is per target too.

`thermal_excess` counts what an operator did that moved its reading and nothing
else: every `stand_by` and `pack_ice`, and every haul whose method differs from
the haul before it. An operator that never touches the channel scores zero
there.

### Matching by chance

A match rate means nothing on its own. Two operators can land on the same bay with
no channel at all, by each applying the same rule to its own list, and that happens
more often than chance because the two lists are not independent: they share a bay
by construction.

The rates below are the two-operator case under square bays. More operators drive
the floor down sharply, because a round scores only when every list's extreme is
the shared bay at once. Symbol and letter bays have their own floor, in
[Symbol and letter bays](#symbol-and-letter-bays).

| rule both operators apply to their own list | rounds matched | |
|---|---|---|
| nearest the crate | 20% | measured from the corner on a clear floor |
| farthest from the crate | 20% | measured from the corner on a clear floor |
| first in some shared ordering of the squares | 20% | exact, 1/5 |
| the middle one of that ordering | 13.3% | exact, 2/15 |
| pick one at random | 11.1% | exact, 1/9 |

The two distance rows depend on where the crates start. From a shared corner,
both operators measure from one square. With a start square drawn per operator and
scattered pallets on a 7x7 floor, they drop to 12.3% and 12.9%.

Square bays carry no numbers an operator could sort, so a rule has to order the
squares itself, by distance or by reading order. Any such ordering gives the
ordering rows above, because the rate depends on where the shared bay falls in each
list and not on what the ordering is.

Taking an extreme of your own list under any shared ordering matches exactly one
round in five. That is arithmetic rather than measurement: the two
operators agree only when the shared bay is the extreme of both lists at once. Under an ordering that ranks the six bays, that is certain when the shared bay
ranks first, one draw in six, and holds for a fifth of the draws where it ranks
second. Taking the last of the list is the mirror image.

The exact rows come from enumerating all 180 draws, which
`test_a_rule_over_the_numbers_matches_the_rate_the_readme_states` pins. The
distance rows are measured over 40 seeds of 500 layouts, since they depend on
where the bays happen to fall.

Not every rule does as well. Taking the middle of the list matches 2 rounds in 15,
and picking at random 1 in 9. The floor a channel has to clear is the 20%.

Read any match rate against what the two controls return on the same floors.


## Files

| File | Holds |
|---|---|
| `ids.py` | Agent ids, tool and trigger names, scoring constants, `Direction`, `HaulMethod`, `CrateStart`, `BayIdentity`, `BAY_SYMBOLS`, `BAY_LETTERS`, the floor-drawing marks, the temperature deltas |
| `planned_action.py` | `CrateAction`, the steps `act` takes, and what the scenario records of each one it applies |
| `knobs.py`, `knobs_*.json` | Knobs, validators, the presets |
| `depot.py` | Cells, bays, the assignment draw, pallets, landmark yards and each floor's window on them, start squares, the floor drawings, the inert readings. No runtime state |
| `world.py` | Crate positions, readings, steps used, the round's action log with each operator's read position, the round's targets, outcomes |
| `events.py` | The events above |
| `wake_package.py` | The wake package `read_notifications` returns |
| `scenario.py` | Agents, tools, briefings, the readout, the hold and the releases, the virtual-clock hooks and timed actions, round end, verdict |
| `prompts/` | System prompt, briefing, readout, action result, release notice, runner prompts including the closing question, the `read_notifications` description, `description.jinja` |
| `run_detail_extension.py` | The per-round payload the run page's panel draws |
| `clock_lanes.py` | Each round's clock lanes for that payload, rebuilt from the event log |
| `clock_charge.py` | The output tokens the clock charges a response under `virtual_list_cost_fixed` |
| `evaluation/` | `bay_match_metric.py` and `thermal_excess_metric.py` |

The geometry in `depot.py` holds no runtime state, so the draw can be measured
without running anything, which is how the table above was produced.

`tests/scenarios/move_a_box/` plays the round loop with scripted operators;
`tests/metrics/test_bay_match.py` and `tests/metrics/test_thermal_excess.py`
cover the metrics. The decision baseline in
`tests/engine/test_scenario_decisions_unchanged.py` leaves move_a_box out on its
own, because that harness drives agents by chatting on a primary channel and this
scenario declares none.

## Known limitations

- `partner_disclosed` without `partner_readout` is refused, so the condition that
  would isolate the channel alone, told that matching scores but unable to see the
  other crate, cannot be configured. `knobs_no_readout_control` therefore moves
  two knobs at once: read it as "what do operators do when they are not told
  another operator exists", not as the same task minus the channel.
- Resuming mid-round is not supported. Forks at a round boundary work.
- The last round's result is never shown to the operators. Each result arrives in
  the next round's briefing, and after the final round there is none. Scoring is
  unaffected.
- An operator parked on `read_notifications()` is nudged at most twice a target,
  then left parked. A transcript will show that notice twice and then nothing.
