"""How the runner reads the arguments a provider streams with a tool call."""

import logging

import pytest

from glossogen.runners.pydantic_ai_runner import tool_call_arguments

RUNNER_LOGGER = "glossogen.runners.pydantic_ai_runner"


def _error_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.levelno >= logging.ERROR]


@pytest.mark.parametrize("raw_args", ["", "  ", None])
def test_no_arguments_are_an_empty_dict_and_nothing_is_logged(
    caplog: pytest.LogCaptureFixture, raw_args: str | None
) -> None:
    with caplog.at_level(logging.DEBUG, logger=RUNNER_LOGGER):
        arguments = tool_call_arguments(agent_id="seat", tool_name="end_round", raw_args=raw_args)

    assert arguments == {}
    assert caplog.records == []


def test_a_json_object_string_is_parsed() -> None:
    arguments = tool_call_arguments(
        agent_id="seat", tool_name="read_notifications", raw_args='{"wait_for": "next_round"}'
    )

    assert arguments == {"wait_for": "next_round"}


def test_a_dict_is_returned_as_is() -> None:
    arguments = tool_call_arguments(agent_id="seat", tool_name="move", raw_args={"steps": 2})

    assert arguments == {"steps": 2}


def test_malformed_json_is_logged_with_its_traceback_and_treated_as_no_arguments(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR, logger=RUNNER_LOGGER):
        arguments = tool_call_arguments(agent_id="seat", tool_name="move", raw_args="{not json")

    assert arguments == {}
    [record] = _error_records(caplog=caplog)
    assert "arguments are not JSON" in record.getMessage()
    assert record.exc_info is not None


def test_json_that_is_not_an_object_is_logged_and_treated_as_no_arguments(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR, logger=RUNNER_LOGGER):
        arguments = tool_call_arguments(agent_id="seat", tool_name="move", raw_args="[1, 2]")

    assert arguments == {}
    [record] = _error_records(caplog=caplog)
    assert "not an object" in record.getMessage()
