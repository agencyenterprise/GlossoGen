"""Frozen EXP-072 structural-revision preregistration checks."""

import hashlib
import json
from pathlib import Path

ROOT = Path("docs/research/covenant-game/experiments/EXP-072-capacity-crossroads-paired-balance")
EXPECTED_HASHES = {
    "configs/campaign.json": "a12f9ed1d47e1698896087170fd381bfafc4486f6d08b75ddf88b2c7e54e85c1",
    "configs/balance/balance_paired_matched_priority_seed-785100.json": (
        "1963fe662d4339aecbde2e94cc3c55e6855eb23fba885d013381fe98ff8af5eb"
    ),
    "configs/balance/balance_paired_matched_priority_seed-785101.json": (
        "20e26f173c68351189272ca0241a9bcda4b95265b275a2b553b748dd3a079d77"
    ),
    "configs/balance/balance_paired_matched_priority_seed-785102.json": (
        "fb5172ddaca3fd4a660d90f61e090a7ddb9692b6954e9a44d11e1e578b961013"
    ),
    "configs/balance/balance_paired_matched_priority_seed-785103.json": (
        "5bf42d6663739f1a8d84bb3ad419a1ed6644fa8fe035bbb275d13badb7b39460"
    ),
    "analysis/summarize_paired_balance.py": (
        "1c396ea28fda1d25e1d4c7ef16c1cc0623179148548f197dbda83b1b60f9f494"
    ),
}


def test_exp072_artifacts_match_preregistered_hashes() -> None:
    """Configs and analysis remain byte-identical after preregistration."""
    for relative_path, expected_hash in EXPECTED_HASHES.items():
        content = (ROOT / relative_path).read_bytes()
        assert hashlib.sha256(content).hexdigest() == expected_hash


def test_exp072_configs_freeze_the_single_structural_revision() -> None:
    """Every launch fixes the same matched-pair arm-A baseline mechanics."""
    paths = sorted((ROOT / "configs" / "balance").glob("*.json"))
    assert len(paths) == 4
    for path in paths:
        config = json.loads(path.read_text(encoding="utf-8"))
        assert config["decision_structure"] == "paired_equal_priority"
        assert config["temptation_strength"] == "matched_priority"
        assert config["arm"] == "A"
        assert config["observation"] == "unobserved"
        assert config["moral_weight"] == "unspecified"
        assert config["action_budget"] == 6
