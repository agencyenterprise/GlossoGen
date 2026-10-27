# carrier_song

Two players take turns sending each other a secret code, such as `7Z2CRV`. They have
no channel and no tool that carries text to the partner. Each round the world plays a
song, a list of whole numbers, and the sender gets the code across by adding noise to
it. The noise comes from an executor the sender writes: Python source defining
`noise(song)`. The receiver reads the recording, which is the song plus that noise
plus channel noise, without ever seeing the song, and submits its decoding.

The question is whether two agents can agree on an encoding when the only medium for
agreeing on it is the channel itself. Round one has no protocol yet; from round two
on, each player can answer the other through its own turn as sender. The run stops at
the first correct decoding, so the number of rounds it took is the result.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run carrier_song \
  --model claude-haiku-5-5 --provider anthropic --runs-dir ./runs \
  --config knobs_default \
  > ./runs/carrier_song_stdout.log 2>&1 &
```

## A round

player_a sends in odd rounds and player_b in even ones.

1. Both players read the briefing. The sender's names the secret: a code of
   `code_length` characters, each a capital letter A-Z or a digit 0-9.
2. The sender reads the song, puts an executor in place, checks the output and calls
   `end_round`. The receiver waits.
3. `end_round` fixes the recording: `song[t] + noise[t] + channel_noise[t]` at every
   tick. The waiting receiver resumes.
4. The receiver reads the recording and submits its decoding, which ends the round.
   The round scores when the decoding equals the secret, and a round that scores ends
   the run.

A lost round is followed by the next one, up to `round_count`. Its briefing tells both
players only that the decoding was wrong, or that none was submitted. It shows neither
the code nor the decoding: the decoding is free text the receiver chooses, so showing
it to the sender would carry a message around the noise.

## The song and the noise

A song is `motif_length` values drawn between `-song_amplitude` and `song_amplitude`,
looped to `song_length` ticks. The players are not told it loops. Channel noise is
Gaussian with `channel_noise_sigma`, rounded to whole numbers. Songs, secrets and
channel noise are drawn from `seed` and the round number alone, not from anything
the players did in earlier rounds.

The executor is Python source defining:

```python
def noise(song):    # song: list[int], song_length long
    return [...]    # list[int], the same length
```

It runs in a fresh interpreter with the standard library only. Each value is clipped
to `±max_volume`. An executor stays in place for its author's later turns as sender,
playing over each new song, until the author replaces it. `write_executor` tests the
new code on the round's song first: if it fails, or returns anything but a list of
whole numbers as long as the song, its error goes back to its author and the
executor already in place stays. When a round opens, the sender's executor in place
runs on the new song before the briefings go out. If it fails there, the sender plays
silence until it puts a new one in place, and its briefing gives the error. A sender
with no executor in place plays silence. The code and what it prints go to its
author alone.

## Tools

| Tool | Role | What it does |
|---|---|---|
| `read_song()` | sender | The round's song |
| `write_executor(code)` | sender, before `end_round` | Tests `code` on the song and puts it in place when it works. Returns the clipped noise, or the error |
| `read_output()` | sender, before `end_round` | The song with the noise added, before channel noise |
| `end_round()` | sender | Fixes the noise and the recording; wakes the receiver |
| `read_received()` | receiver, after `end_round` | The recording. Under `receiver_sees_song`, also the song |
| `submit_decoding(secret)` | receiver, after `end_round` | The receiver's reading of the code, once per round. Whitespace is stripped and letters capitalised; a reading that is not `code_length` characters from A-Z and 0-9 is refused and does not count. An accepted one ends the round |
| `run_python(code)` | either | Runs a program in a fresh interpreter. Its working directory holds what the caller can see as JSON lists: `song.json` for the sender (and the receiver under `receiver_sees_song`), `received.json` for the receiver once the recording is fixed |
| `read_notifications()` | either | At startup and after a round changes, the briefing. The receiver uses it to wait for the recording |
| `read_notifications(wait_for="next_round")` | either | Waits for the next briefing |

Every player is offered every tool, since the roles swap. A call from the wrong role
is refused with a message saying whose tool it is. `hidden_base_tools` withholds
`send_message`, `read_channel`, `list_channels` and `get_channel_members`, and
`validate_outgoing_message` refuses any message.

A resumed `read_notifications` returns a JSON wake package: `type` (`done` once the
game is over), `round`, `wake_reasons`, `briefings` and `notice`.

### Waiting

A plain `read_notifications()` has no default timeout. `end_round` resumes a
receiver that is waiting, and a receiver that parks once the recording is ready is
resumed at once, with a notice to read it. A sender that waits before calling
`end_round` would wait forever, since the receiver is waiting for it: it is released
with a notice saying so. The hook releases each player at most twice a round. Past
that the player stays parked, and with both parked the round ends.

## Knobs

| Knob | Default | Effect |
|---|---|---|
| `song_length` | 64 | Ticks per song |
| `motif_length` | 8 | Length of the loop each song repeats |
| `song_amplitude` | 6 | Song values lie within `±song_amplitude` |
| `max_volume` | 2 | The sender's noise is clipped to `±max_volume` per tick |
| `channel_noise_sigma` | 1.0 | Standard deviation of the channel noise; 0 turns it off |
| `code_length` | 6 | Characters in the secret code, each from A-Z and 0-9 |
| `receiver_sees_song` | false | Shows the receiver the song under the recording, so decoding becomes a subtraction |
| `seed` | 42 | Songs, secrets and channel noise |

A code of `code_length` characters carries about `5.17 × code_length` bits, so the
default's 6 characters are about 31 bits in 64 ticks. Under the default knobs each
tick carries at most ±2 of noise on top of a song of up to ±6 that the receiver never
sees, plus channel noise of σ 1. A receiver that reads ticks one at a time has to
estimate the song first. Pairing each tick with the tick one loop later, at
`+max_volume` and `-max_volume`, cancels the song exactly when the receiver subtracts
the two, but only a pair that finds the loop can use it.

The preset sets `parallel_tool_calls: false`, so a sender sees each tool result
before its next call. Postmortem and compaction are refused: both talk about
channels, and the run has none.

## Measurement

`is_finished_early` stops the game clock after the first round whose decoding equals
the secret, once that round's verdict is recorded. Later rounds are not played and
record no result. The number of rounds a run played is its measure: a run that
reached `round_count` with every round lost never got a secret across. In a
multi-run export that number is the `metric_rounds.round_success` column. Read
`round_success` itself with that in mind, since it is 1 over the rounds played for a
run that won and 0 for one that did not.

`get_primary_channels()` is empty, so the text metrics skip. The protocol the players
settle on is in the event log: every executor each sender wrote, the noise it played
and the recording the receiver got.

## Events

| Event | Holds |
|---|---|
| `carrier_song_round_started` | Sender, receiver, secret, song and channel noise |
| `carrier_song_executor_ran` | One executor run: the code, whether it was just written or already in place, whether it was accepted, the clipped noise and the error |
| `carrier_song_transmitted` | The noise the sender played and the recording |
| `carrier_song_decoding_submitted` | The receiver's decoding |
| `carrier_song_round_resolved` | Secret, decoding, success and the trigger that ended the round |

## Limits

Executors and `run_python` programs run through `glossogen.code_sandbox`. Its
interpreter has the standard library only, a fresh working directory holding just
the input files, and caps on CPU time, file size and processes. As that module says,
it protects the simulation from a program's accidents, not from a program written to
reach past it: a program keeps the network and can read files outside its working
directory as the user running the simulation. Nothing here checks programs for that.
