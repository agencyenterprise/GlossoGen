# signal_game_carrier

The signal game played over a radio channel. Two players each hold a private grid of
coloured squares and win a round by picking squares of the same colour. Nothing carries
text between them: the only link is noise they add to a song.

## A round

1. The world draws two grids, one per player, and a song of `song_length` whole numbers.
   The two grids always share at least one colour.
2. Both players read the song with `read_song()`.
3. Each player puts an executor in place with `write_executor(code)`: Python source
   defining `noise(song)`, run in the sandbox, its return value clipped to
   `±max_volume`. The executor stays in place for later rounds until its author
   replaces it, playing over each new song.
4. Each player calls `transmit()`, which fixes its noise for the round.
5. Once both have transmitted, `read_recording()` returns the song, both players' noise
   and Gaussian channel noise, added tick by tick.
6. Each player calls `end_round(row, col)` on its own grid. The round scores when the
   two squares hold the same colour.

A player knows the song and its own noise, so subtracting both from the recording leaves
its partner's noise plus the channel's hiss. What a noise pattern stands for is not given
to them. The next round's briefing tells both players which colour each picked and
whether the round was won, which is the only feedback they get.

## Knobs

`grid_size` and `colour_count` set the grids. `song_length`, `motif_length` and
`song_amplitude` set the song: a motif, looped. `max_volume` clips each player's noise
per tick, and `channel_noise_sigma` sets the hiss. `seed` fixes the grids, the songs and
the hiss for every round.

`prompt_detail` picks the wording of everything the players read. `lean`, which
`knobs_default` uses, says what the game is and what each tool does. `full`, in
`knobs_full_prompt`, also spells out how the noise is combined with the song, the volume
limit and what the recording is made of.

## How it differs from carrier_song

Both scenarios put a radio between the players, and each carries its own copy of the
song draws, the sandbox harness and the executor runner, so neither constrains the
other. The difference is the task and the traffic: carrier_song has one sender
transmitting a secret code to one receiver, while here both players transmit into the
same recording and both have to act on what they hear.

## The run page

The round-timeline modal draws each round: both players' grids with the square each
picked ringed, the song over the recording, a bar strip per player for the noise it
added, the channel noise, and each executor's source.

## Running it

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run signal_game_carrier \
  --model gpt-6.1-sol --provider openai --runs-dir ./runs --config knobs_default
```
