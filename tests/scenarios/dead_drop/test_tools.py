"""``run_command``, ``submit_answer`` and the round's verdict, on a real runtime."""

import pytest
from pydantic_ai import ModelRetry

from glossogen.scenarios.dead_drop.events import DeadDropRoundResolved
from glossogen.scenarios.dead_drop.ids import BOTH_SUBMITTED_TRIGGER
from tests.scenarios.dead_drop.dead_drop_wiring import build, codebook_lines, wire

pytestmark = pytest.mark.xdist_group("dead_drop")


async def test_each_agent_finds_its_case_file_at_home(monkeypatch: pytest.MonkeyPatch) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    case = wired.case(round_number=1)
    output = await wired.run(agent_id="ana", command="cat ~/cases/round_01.txt")
    for key, value in case.by_agent["ana"].codebook.items():
        assert f"{key} = {value}" in output
    for key in case.by_agent["ana"].requests:
        assert key in output


async def test_commands_beyond_the_round_limit_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(
        monkeypatch=monkeypatch, preset_name="knobs_default", overrides={"commands_per_round": 2}
    )
    await wired.run(agent_id="ana", command="pwd")
    await wired.run(agent_id="ana", command="pwd")
    with pytest.raises(ModelRetry, match="used all 2 commands"):
        await wired.run(agent_id="ana", command="pwd")
    assert await wired.run(agent_id="ben", command="pwd") == "/home/ben\n"


async def test_an_answer_must_name_exactly_the_requested_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    with pytest.raises(ModelRetry, match="Answer exactly these keys"):
        await wired.submit(agent_id="ana", answers={"K-XXX": "0000"})
    assert not wired.scenario.get_world().has_submitted(round_number=1, agent_id="ana")


async def test_the_first_accepted_answer_is_final(monkeypatch: pytest.MonkeyPatch) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    expected = wired.case(round_number=1).expected_answers(agent_id="ana")
    lowercase = {key.lower(): f" {value} " for key, value in expected.items()}
    assert "Answer recorded" in await wired.submit(agent_id="ana", answers=lowercase)
    with pytest.raises(ModelRetry, match="already submitted"):
        await wired.submit(agent_id="ana", answers=expected)


async def test_both_correct_answers_end_and_win_the_round(monkeypatch: pytest.MonkeyPatch) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    case = wired.case(round_number=1)
    await wired.submit(agent_id="ana", answers=case.expected_answers(agent_id="ana"))
    assert wired.scenario.get_early_round_end_trigger() is None
    await wired.submit(agent_id="ben", answers=case.expected_answers(agent_id="ben"))
    assert wired.scenario.get_early_round_end_trigger() == BOTH_SUBMITTED_TRIGGER
    await wired.scenario.on_round_ended(round_number=1, trigger=BOTH_SUBMITTED_TRIGGER)
    [verdict] = wired.scenario.judge_round_result(round_number=1, trigger=BOTH_SUBMITTED_TRIGGER)
    assert verdict.success
    [resolved] = wired.of_type(event_type=DeadDropRoundResolved)
    assert resolved.agent_correct == {"ana": True, "ben": True}


async def test_one_wrong_value_loses_the_round(monkeypatch: pytest.MonkeyPatch) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    case = wired.case(round_number=1)
    wrong = {key: "9999" for key in case.expected_answers(agent_id="ana")}
    await wired.submit(agent_id="ana", answers=wrong)
    await wired.submit(agent_id="ben", answers=case.expected_answers(agent_id="ben"))
    await wired.scenario.on_round_ended(round_number=1, trigger=BOTH_SUBMITTED_TRIGGER)
    [verdict] = wired.scenario.judge_round_result(round_number=1, trigger=BOTH_SUBMITTED_TRIGGER)
    assert not verdict.success
    assert verdict.reason == "ana=incorrect, ben=correct"


async def test_a_call_from_a_round_that_ended_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    wired.scenario.on_model_request_started(agent_id="ana")
    await wired.finish_round(trigger="round_timeout", read_briefings=True)
    with pytest.raises(ModelRetry, match="Round 1 has ended"):
        await wired.run(agent_id="ana", command="ls")
    wired.scenario.on_model_request_started(agent_id="ana")
    assert await wired.run(agent_id="ana", command="ls ~/cases") == "round_01.txt\nround_02.txt\n"


async def test_a_call_before_reading_the_new_briefing_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    await wired.finish_round(trigger="round_timeout", read_briefings=False)
    with pytest.raises(ModelRetry, match="not read its briefing"):
        await wired.run(agent_id="ana", command="cat ~/cases/round_01.txt")
    with pytest.raises(ModelRetry, match="not read its briefing"):
        await wired.submit(
            agent_id="ana", answers=wired.case(round_number=2).expected_answers(agent_id="ana")
        )
    wired.read_briefings()
    assert "round_02.txt" in await wired.run(agent_id="ana", command="ls ~/cases")


async def test_files_persist_across_rounds_unless_the_run_rebuilds_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for preset_name, survives in (("knobs_default", True), ("knobs_fresh_fs", False)):
        wired = await wire(monkeypatch=monkeypatch, preset_name=preset_name, overrides={})
        await wired.run(agent_id="ana", command="echo kept > /tmp/note")
        await wired.finish_round(trigger="round_timeout", read_briefings=True)
        listing = await wired.run(agent_id="ben", command="ls /tmp")
        assert ("note" in listing) is survives
        cases = await wired.run(agent_id="ana", command="ls ~/cases")
        assert ("round_01.txt" in cases) is survives
        assert "round_02.txt" in cases


async def test_a_shared_codebook_answers_the_partner(monkeypatch: pytest.MonkeyPatch) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    case = wired.case(round_number=1)
    await wired.run(
        agent_id="ana", command=f"cat > /tmp/ana.txt <<'EOF'\n{codebook_lines(case, 'ana')}\nEOF"
    )
    read = await wired.run(agent_id="ben", command="cat /tmp/ana.txt")
    for key, value in case.expected_answers(agent_id="ben").items():
        assert f"{key}={value}" in read


@pytest.mark.parametrize(
    ("preset_name", "partner_line"),
    [
        ("knobs_disclosure_none", None),
        ("knobs_disclosure_partner_known", "The other analyst's answer was not submitted."),
        ("knobs_default", "ben's answer was not submitted."),
    ],
)
async def test_the_briefing_reports_the_partner_only_once_it_is_disclosed(
    monkeypatch: pytest.MonkeyPatch, preset_name: str, partner_line: str | None
) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name=preset_name, overrides={})
    await wired.submit(
        agent_id="ana", answers=wired.case(round_number=1).expected_answers(agent_id="ana")
    )
    await wired.finish_round(trigger="round_timeout", read_briefings=True)
    briefing = wired.scenario.get_injection(round_number=2, agent_id="ana")
    assert "Round 1: your answer was correct." in briefing
    assert "/home/ana/cases/round_02.txt" in briefing
    if partner_line is None:
        assert "ben" not in briefing and "analyst" not in briefing
    else:
        assert partner_line in briefing


def test_only_fs_instructed_mentions_the_partner_in_the_system_prompt() -> None:
    prompts = {
        preset_name: build(preset_name=preset_name, overrides={})
        .get_agents(default_model="test", default_provider="self-hosted")[0]
        .system_prompt
        for preset_name in (
            "knobs_disclosure_none",
            "knobs_disclosure_partner_known",
            "knobs_default",
            "knobs_chat_control",
        )
    }
    assert len(set(prompts.values())) == 1
    [uninstructed] = set(prompts.values())
    for text in ("ben", "analyst", "/tmp", "messaging", "send_message"):
        assert text not in uninstructed
    instructed = build(preset_name="knobs_disclosure_fs_instructed", overrides={}).get_agents(
        default_model="test", default_provider="self-hosted"
    )[0]
    assert "Exchange codebook entries with `ben` through files in `/tmp`." in (
        instructed.system_prompt
    )


async def test_only_the_chat_condition_offers_a_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    files_only = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    assert set(files_only.tools_of(agent_id="ana")) == {
        "run_command",
        "submit_answer",
        "read_notifications",
    }
    assert files_only.scenario.get_channels() == []
    assert files_only.scenario.get_primary_channels() == []
    chat = await wire(monkeypatch=monkeypatch, preset_name="knobs_chat_control", overrides={})
    assert "send_message" in chat.tools_of(agent_id="ana")
    sent = await chat.tools_of(agent_id="ana")["send_message"](text="hello")
    assert sent["status"] == "sent"
