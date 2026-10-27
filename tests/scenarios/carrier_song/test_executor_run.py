"""A sender's executor run in the sandbox: the noise it returns, clipped, or why it failed."""

import signal

from glossogen.scenarios.carrier_song.executor_run import exit_description, run_executor

SONG = [3, -1, 4, 1]


async def test_the_noise_comes_back_with_what_the_executor_printed() -> None:
    code = "def noise(song):\n    print('hello')\n    return [value * -1 for value in song]\n"

    run = await run_executor(code=code, song=SONG, max_volume=10)

    assert run.error is None
    assert run.noise == [-3, 1, -4, -1]
    assert run.clipped_ticks == 0
    assert run.printed == "hello\n"


async def test_values_past_the_volume_are_clipped_and_counted() -> None:
    code = "def noise(song):\n    return [9, -9, 1, 0]\n"

    run = await run_executor(code=code, song=SONG, max_volume=2)

    assert run.noise == [2, -2, 1, 0]
    assert run.clipped_ticks == 2


async def test_a_list_of_the_wrong_length_is_refused() -> None:
    run = await run_executor(code="def noise(song):\n    return [0]\n", song=SONG, max_volume=2)

    assert run.noise is None
    assert run.error == "noise(song) returned 1 values; the song has 4 ticks"


async def test_a_value_that_is_not_a_whole_number_is_refused() -> None:
    code = "def noise(song):\n    return [0, 0.5, 0, 0]\n"

    run = await run_executor(code=code, song=SONG, max_volume=2)

    assert run.noise is None
    assert run.error is not None
    assert run.error.startswith("noise(song)[1] is 0.5")


async def test_booleans_are_not_whole_numbers() -> None:
    code = "def noise(song):\n    return [True, 0, 0, 0]\n"

    run = await run_executor(code=code, song=SONG, max_volume=2)

    assert run.noise is None


async def test_a_program_without_noise_says_so() -> None:
    run = await run_executor(code="x = 1\n", song=SONG, max_volume=2)

    assert run.noise is None
    assert run.error == "noise.py defines no function named noise"


async def test_an_exception_comes_back_as_its_traceback() -> None:
    code = "def noise(song):\n    raise RuntimeError('broken')\n"

    run = await run_executor(code=code, song=SONG, max_volume=2)

    assert run.noise is None
    assert run.error is not None
    assert "RuntimeError: broken" in run.error


async def test_a_syntax_error_comes_back_as_its_traceback() -> None:
    run = await run_executor(code="def noise(song)\n", song=SONG, max_volume=2)

    assert run.noise is None
    assert run.error is not None
    assert "SyntaxError" in run.error


async def test_a_tuple_is_not_a_list() -> None:
    code = "def noise(song):\n    return (1,) * len(song)\n"

    run = await run_executor(code=code, song=SONG, max_volume=2)

    assert run.noise is None
    assert run.error is not None
    assert "noise(song) must return a list, not tuple" in run.error


async def test_an_executor_killed_by_a_limit_says_which() -> None:
    code = "import os, signal\n\ndef noise(song):\n    os.kill(os.getpid(), signal.SIGXCPU)\n"

    run = await run_executor(code=code, song=SONG, max_volume=2)

    assert run.noise is None
    assert run.error == "the executor ended: stopped by the CPU limit of 5 seconds"


def test_an_ending_names_the_limit_or_the_signal() -> None:
    assert exit_description(exit_status=1) == "exit status 1"
    assert exit_description(exit_status=-signal.SIGXCPU) == "stopped by the CPU limit of 5 seconds"
    assert (
        exit_description(exit_status=-signal.SIGXFSZ)
        == "stopped by the file size limit of 1048576 bytes"
    )
    assert exit_description(exit_status=-signal.SIGKILL) == "stopped by SIGKILL"
