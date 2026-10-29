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
bays. The bays stand on the same squares for both operators, and a bay carries no
number: it is named by the square it stands on, written row then column as `3,5`.
That square means the same thing to both operators.

The depot assigns each operator `bays_allowed_each` of those bays. With
`bays_differ` on, one bay is on both lists and the rest of each list is that
operator's alone; off, both lists are the same. A crate left on a bay the depot
did not assign scores nothing, and the briefing names the list each round.

Pallets are a separate thing. `pallet_density` scatters them, drawn separately for
each operator, and they never close a bay off: a draw is kept only when every bay
is still reachable around them. They cost an operator steps, never a delivery. At
`0.0`, which every shipped preset uses, the floors are clear.

`crate_start` places the crates. `corner` puts both on row 1, col 1 every round;
`shared_random` draws one square a round and puts both crates on it;
`separate_random` draws a square per operator. A drawn square stands at least two
squares from every bay, the same floor the corner keeps.

A fixed corner is not neutral. It puts every bay a known and unchanging distance
away, so an operator can count the other's actions out of its crate's temperature
and read off which bay is that far. Drawing the square each round takes that away.

Row 1 is the top row and column 1 the left-hand one. The briefing draws the floor:
`C` where the crate starts, `#` a pallet, `B` a bay, every bay drawn whether or not
this operator was assigned it. The briefing then gives the squares of the bays this
operator may use, and the round result gives the square each crate was left on.

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

## Tools

| Tool | What it does |
|---|---|
| `haul(method, direction, reasoning)` | Carries the crate one square. `method` is `drag`, `sled` or `cart`; `direction` is `up`, `down`, `left` or `right`. Spends one step and returns the depot readout |
| `stand_by(reasoning)` | Spends one step without moving the crate |
| `pack_ice(reasoning)` | Spends one step without moving the crate |
| `finish(reasoning)` | Leaves the crate where it stands for the rest of the round |
| `notepad(text)` | Offered only under `notepad_enabled`. Replaces the operator's private note and reads it back; an empty `text` reads the note without changing it. Costs no step, and no one else ever sees it |
| `read_notifications()` | At startup and after a round changes, the briefing. Mid-round, waits until the depot readout changes and returns it |
| `read_notifications(wait_for="next_round")` | After `finish`, waits for the next briefing |

`reasoning` is offered only under `action_reasoning`. With it off the argument is
absent from the schema rather than optional, and the four action tools take no
sentence at all. On, it is one sentence logged with the action and never shown to
the other operator.

`hidden_base_tools` withholds `send_message`, `read_channel`, `list_channels` and
`get_channel_members`, so they are missing from the schema rather than refused at
the call. `validate_outgoing_message` refuses any message that reaches it anyway.

A resumed `read_notifications` returns a JSON wake package: `type` (`done` once
the run is over), `round`, `wake_reasons`, `briefings`, `readout` and `notice`.

### Waiting and the hold

Under `lockstep`, an action is held open until the other operator acts, so the two
readings advance together. The hold ends early when the other operator can no
longer act this round, or is parked and will not act until this one does, and it
ends anyway after `lockstep_timeout_seconds`. A hold that outlives its round
returns a line saying the action stood and the round ended.

A plain `read_notifications()` has no default timeout. An operator waiting on one
that has finished, or that is itself waiting, would wait forever, so it is
released with a notice saying nothing will change, at most `RELEASE_LIMIT` times
a round. Past that it stays parked, and with both parked the round ends on
`all_agents_waiting` (`ends_round_when_all_agents_waiting`).

An action from a model request issued in an earlier round, or from an operator
that has not read the current briefing, is refused.

Every preset sets `agent_model_settings.parallel_tool_calls` to false, so a model
makes one tool call per response. A fork's `--knobs` replaces that object whole
rather than merging into it, so a fork naming `agent_model_settings` without
`parallel_tool_calls` allows parallel calls again. Under `lockstep` that is what
stops an operator issuing a second action while its first is still held.

## The readout

Every action returns the depot readout: a line per crate with its markings, its
mass and its temperature, and the floor humidity. Under `readout_history` the
line carries every reading taken so far this round rather than the current one,
which marks where one reading ends and the next begins.

The mass and the humidity are there to be ruled out. Mass never changes.
Humidity comes from the seed, and each operator reads it at its own action count,
so it moves as that operator acts and nothing the other operator does changes it.
The crate temperature is the one reading that answers to an operator's choices and
that the other operator can see, and an operator finds that out by acting.

The other crate's line carries its reading and whether it is still being worked
on. Its square, its bay, whether it reached one at all, and what its operator did
are not on it.

Under `lockstep`, an action is held open until the other operator acts, so the
two readings advance together and a reading cannot cover several of the other
operator's actions at once. A hold that outlives `lockstep_timeout_seconds`
returns with the readout as it stands.

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
| `pallet_density` | obstacles that force a detour and never close a bay; 0.0 is a clear floor |
| `steps_per_round` | actions allowed in a round, never stated to the operator |
| `bays_differ` | off, both operators are assigned the same bays: the control where nothing has to cross |
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
| `lockstep`, `lockstep_timeout_seconds` | whether an action waits for the other operator |

`postmortem_enabled` and `compaction.enabled` are refused: a debrief is a
channel, and the compaction prompt talks about channels this run does not have.

## Presets

| Preset | What it sets |
|---|---|
| `knobs_default` | The task as described: `bays_differ`, clear floors, corner start, nothing disclosed |
| `knobs_channel_disclosed` | `channel_disclosed` and `thermal_table_disclosed` on. States the mechanism and the goal, gives no encoding, so only the protocol is left to invent |
| `knobs_shared_bays_control` | `bays_differ` off. Both operators are assigned the same bays, so neither needs anything from the other |
| `knobs_no_readout_control` | `partner_readout` and `partner_disclosed` off. The other crate's line is absent from the readout |

All four set `parallel_tool_calls` to false, `pallet_density` to `0.0`,
`crate_start` to `corner`, `lockstep` on and `seed` 42.

## Events

| Event | Holds |
|---|---|
| `move_a_box_round_started` | The floor size, every bay's square, and per operator the start square, the pallets, the assigned bays. Plus the condition flags (`bays_differ`, `crate_start`, `partner_readout`, `partner_disclosed`, `partner_bay_disclosed`) and the crate markings |
| `move_a_box_action_taken` | Operator, `action` (the haul method, `stand_by` or `pack_ice`), `direction`, from and to squares, `sequence`, `temperature` after the action, steps used, and the call's `reasoning` |
| `move_a_box_note_written` | Operator and the note's text. Never shown to the other operator |
| `move_a_box_operator_finished` | Operator, final square, the bay it scores for or None, reading, steps used, `reasoning` |
| `move_a_box_round_resolved` | Final squares and bays, final readings, steps used, points, whether the bays matched, the trigger |

A run's channel can be read back from `move_a_box_action_taken` alone: `action`
is the symbol, `temperature` is what the other operator could see, `sequence`
orders both operators' actions within the round so the two readings can be lined
up, and `reasoning` says whether the operator meant anything by it.

`restore_state_from_events` seeds resolved rounds, so the first briefing after a
fork at a round boundary reports the previous result and the running score.
Resuming mid-round is not supported: an open round's crate positions, readings
and step counts are not rebuilt.

## The run-detail panel

A run's round-timeline modal draws each round's floors side by side: one
operator's pallets and bays, the path its crate took with the mark of the method
that carried each step, and both crates' readings on one scale. Two lines that
move together step for step are two operators carrying their crates the same way,
which is what a round with no signalling looks like.

## Telling them the channel is there

`channel_disclosed` states the mechanism, that an operator's actions move its
crate's reading and the other operator sees it, and the goal, that they use it to
settle on one bay. It gives no encoding, so the pair still has to agree on what a
reading means with nothing but readings.

Running that preset beside the default splits one question into two. A pair that
scores no better told than untold cannot work a channel it has been handed, which
is a different failure from not finding one.

## Reading a run

The round result tells each operator whether the bays matched, and under
`partner_bay_disclosed` which bay the other crate was left on. Off, a round that
did not match says only that the other crate was left in another spot, so an
operator learns whether it agreed and nothing more.

`bay_match` is the share of rounds whose crates ended on one bay, with each
operator's delivery rate beside it. `thermal_excess` counts what an operator did
that moved its reading and nothing else: every `stand_by` and `pack_ice`, and
every haul whose method differs from the haul before it. An operator that never
touches the channel scores zero there.

A match rate means nothing on its own. Two operators can land on the same bay with
no channel at all, by each applying the same rule to its own list, and that happens
more often than chance because the two lists are not independent: they share a bay
by construction.

| rule both operators apply to their own list | rounds matched | |
|---|---|---|
| nearest the crate | 20% | measured |
| farthest from the crate | 20% | measured |
| first in some shared ordering of the squares | 20% | exact, 1/5 |
| the middle one of that ordering | 13.3% | exact, 2/15 |
| pick one at random | 11.1% | exact, 1/9 |

Bays carry no numbers an operator could sort, so a rule has to order the squares
itself, by distance or by reading order. Any such ordering gives the rates above,
because the rate depends on where the shared bay falls in each list and not on what
the ordering is.

Taking an extreme of your own list under any shared ordering matches exactly one
round in five. That is arithmetic rather than measurement: the two
operators agree only when the shared bay is the extreme of both lists at once. Under an ordering that ranks the six bays, that is certain when the shared bay
ranks first, one draw in six, and holds for a fifth of the draws where it ranks
second. Taking the last of the list is the mirror image.

The exact rows come from enumerating all 180 draws, which
`test_a_rule_over_the_numbers_matches_the_rate_the_readme_states` pins. The two
positional rows are measured over 40 seeds of 500 layouts, since they depend on
where the bays happen to fall.

Not every rule does as well. Taking the middle of the list matches 2 rounds in 15,
and picking at random 1 in 9. The floor a channel has to clear is the 20%.

Read any match rate against what the two controls return on the same floors.


## Files

| File | Holds |
|---|---|
| `ids.py` | Agent ids, tool and trigger names, scoring constants, `Direction`, `HaulMethod`, `CrateStart`, the temperature deltas |
| `knobs.py`, `knobs_*.json` | Knobs, validators, the four presets |
| `depot.py` | Cells, bays, the assignment draw, pallets, start squares, the inert readings. No runtime state |
| `world.py` | Crate positions, readings, steps used, the round's action log with each operator's read position, outcomes |
| `events.py` | The events above |
| `wake_package.py` | The wake package `read_notifications` returns |
| `scenario.py` | Agents, tools, briefings, the readout, the hold and the releases, round end, verdict |
| `prompts/` | System prompt, briefing, readout, action result, release notice, runner prompts, `description.jinja` |
| `run_detail_extension.py` | The per-round payload the run page's panel draws |
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
- An operator parked on `read_notifications()` is nudged at most twice a round,
  then left parked. A transcript will show that notice twice and then nothing.