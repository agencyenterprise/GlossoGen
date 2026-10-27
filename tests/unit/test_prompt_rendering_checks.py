"""The conformance checks that render a scenario's probe and explanation prompts.

Both template families are rendered only during evaluation, after a paid run has
finished, and the probe family splits its contract across two files: the question
bank is JSON and the prompt is Jinja. A key renamed in one and not the other
raises where nobody is watching.

Each test points a real scenario at a tree built under ``tmp_path`` and asserts
what the check says. Nothing the repository ships is edited, because the suite
runs in parallel against one filesystem.
"""

import json
from pathlib import Path

import pytest

from glossogen.evaluation.metric_core.protocol_explanation_config import (
    ProtocolExplanationConfig,
)
from glossogen.evaluation.metric_core.protocol_probe_config import ProtocolProbeConfig
from glossogen.scenario_authoring.scenario_conformance import CheckOutcome, check_scenario
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.prisoners_dilemma.scenario import PrisonersDilemmaScenario
from glossogen.scenarios.veyru.scenario import VeyruScenario

PROBE = "probe prompts render for every question"
EXPLANATION = "explanation prompts render"


def outcomes_for(check_name: str, scenario_cls: type[SimulationScenario]) -> list[CheckOutcome]:
    """Return what one named check said, across every preset the scenario ships."""
    found = [
        outcome
        for outcome in check_scenario(scenario_cls=scenario_cls)
        if outcome.check == check_name
    ]
    assert found, f"no check named {check_name!r} ran against {scenario_cls.name()}"
    return found


def failure_detail(check_name: str, scenario_cls: type[SimulationScenario]) -> str:
    """Assert the named check failed, and return what the first failure said."""
    broken = [one for one in outcomes_for(check_name, scenario_cls) if not one.passed]
    assert broken, f"{check_name!r} passed against a scenario it should have rejected"
    return broken[0].detail


def passes(check_name: str, scenario_cls: type[SimulationScenario]) -> bool:
    """Whether the named check passed against every preset."""
    return all(outcome.passed for outcome in outcomes_for(check_name, scenario_cls))


def probe_tree(tmp_path: Path, template_body: str, inputs: dict[str, str]) -> ProtocolProbeConfig:
    """A one-question bank and the template its role filter registers."""
    prompts = tmp_path / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / "engineer_probe.jinja").write_text(template_body, encoding="utf-8")
    bank = tmp_path / "questions.json"
    bank.write_text(
        json.dumps([{"id": "q0", "agent_role_filter": "engineer", "inputs": inputs}]),
        encoding="utf-8",
    )
    return ProtocolProbeConfig(
        questions_path=bank,
        prompts_dir=prompts,
        role_groups={"engineer": frozenset({"Stabilization Engineer"})},
        role_templates={"engineer": "engineer_probe.jinja"},
    )


def explanation_tree(tmp_path: Path, template_body: str) -> ProtocolExplanationConfig:
    """One registered explanation template, which the metric renders with no variables."""
    prompts = tmp_path / "explain"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / "engineer_describe.jinja").write_text(template_body, encoding="utf-8")
    return ProtocolExplanationConfig(
        prompts_dir=prompts,
        role_groups={"engineer": frozenset({"Stabilization Engineer"})},
        role_templates={"engineer": "engineer_describe.jinja"},
    )


def declare_probe_config(monkeypatch: pytest.MonkeyPatch, config: ProtocolProbeConfig) -> None:
    """Make every Veyru instance return this probe config."""

    def hook(scenario: VeyruScenario) -> ProtocolProbeConfig:  # noqa: ARG001
        return config

    monkeypatch.setattr(VeyruScenario, "get_protocol_probe_config", hook)


def declare_explanation_config(
    monkeypatch: pytest.MonkeyPatch, config: ProtocolExplanationConfig
) -> None:
    """Make every Veyru instance return this explanation config."""

    def hook(scenario: VeyruScenario) -> ProtocolExplanationConfig:  # noqa: ARG001
        return config

    monkeypatch.setattr(VeyruScenario, "get_protocol_explanation_config", hook)


def test_the_shipped_probe_bank_renders_its_templates() -> None:
    """Asserted on a real scenario, so the check is known to reach a bank at all."""
    assert passes(PROBE, VeyruScenario)


def test_the_shipped_explanation_templates_render() -> None:
    assert passes(EXPLANATION, VeyruScenario)


def test_a_scenario_declaring_neither_config_passes() -> None:
    """Most scenarios return None from both hooks and must not be reported."""
    assert passes(PROBE, PrisonersDilemmaScenario)
    assert passes(EXPLANATION, PrisonersDilemmaScenario)


def test_a_question_missing_an_input_the_template_reads_is_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The failure the split between JSON and Jinja produces."""
    config = probe_tree(
        tmp_path=tmp_path,
        template_body="You saw {{ symptom }} on {{ unit }}.\n",
        inputs={"symptom": "a stall"},
    )
    declare_probe_config(monkeypatch=monkeypatch, config=config)

    detail = failure_detail(PROBE, VeyruScenario)

    assert "q0" in detail
    assert "unit" in detail


def test_a_question_whose_filter_registers_no_template_is_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The metric skips those questions, so reporting them would be a false alarm."""
    config = probe_tree(
        tmp_path=tmp_path,
        template_body="You saw {{ symptom }}.\n",
        inputs={"symptom": "a stall"},
    )
    declare_probe_config(monkeypatch=monkeypatch, config=config._replace(role_templates={}))

    assert passes(PROBE, VeyruScenario)


def test_an_explanation_template_reading_a_variable_is_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The metric renders these with no variables at all."""
    config = explanation_tree(tmp_path=tmp_path, template_body="Describe {{ protocol }}.\n")
    declare_explanation_config(monkeypatch=monkeypatch, config=config)

    detail = failure_detail(EXPLANATION, VeyruScenario)

    assert "engineer_describe.jinja" in detail
    assert "protocol" in detail
