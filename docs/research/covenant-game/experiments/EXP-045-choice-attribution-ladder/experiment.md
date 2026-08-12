# EXP-045 — Choice attribution in response to partner non-contribution

**Status:** complete
**Date opened:** 2026-08-13
**Date closed:** 2026-08-13
**Research program:** covenant-game
**Study:** STUDY-013 — Choice attribution in response to partner non-contribution
**Role:** calibration

<!-- experiment-record:v2
{
  "base_commit": "301b856a9eb20ee25705ed7d51424f5c38aa6345",
  "commands": [
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run pledge_breach --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-045-choice-attribution-ladder/configs/knobs_no_group.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run pledge_breach --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-045-choice-attribution-ladder/configs/knobs_group.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run pledge_breach --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-045-choice-attribution-ladder/configs/knobs_pledge.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run pledge_breach --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-045-choice-attribution-ladder/configs/knobs_cost.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run pledge_breach --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-045-choice-attribution-ladder/configs/knobs_covenant.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run pledge_breach --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-045-choice-attribution-ladder/configs/knobs_covenant_incapacity.json"
  ],
  "configs": [
    {
      "launch_path": "docs/research/covenant-game/experiments/EXP-045-choice-attribution-ladder/configs/knobs_no_group.json",
      "path": "docs/research/covenant-game/experiments/EXP-045-choice-attribution-ladder/configs/knobs_no_group.json",
      "sha256": "15f8bd55041945c92ba297e4d7dfad8197408ba53d416af653abd07d979538d8"
    },
    {
      "launch_path": "docs/research/covenant-game/experiments/EXP-045-choice-attribution-ladder/configs/knobs_group.json",
      "path": "docs/research/covenant-game/experiments/EXP-045-choice-attribution-ladder/configs/knobs_group.json",
      "sha256": "74f5969e81cd0bafd780769d47804d1f604f5643a2f44a33810876dac2bc10c3"
    },
    {
      "launch_path": "docs/research/covenant-game/experiments/EXP-045-choice-attribution-ladder/configs/knobs_pledge.json",
      "path": "docs/research/covenant-game/experiments/EXP-045-choice-attribution-ladder/configs/knobs_pledge.json",
      "sha256": "c783242541475da5152cf44d4a737f1422ab98d7f9004c3401d44712ba1a10a0"
    },
    {
      "launch_path": "docs/research/covenant-game/experiments/EXP-045-choice-attribution-ladder/configs/knobs_cost.json",
      "path": "docs/research/covenant-game/experiments/EXP-045-choice-attribution-ladder/configs/knobs_cost.json",
      "sha256": "47402673a0cb6c51e7edcb495b9e42308fdd32b5ab8724b5d82df837f9b08829"
    },
    {
      "launch_path": "docs/research/covenant-game/experiments/EXP-045-choice-attribution-ladder/configs/knobs_covenant.json",
      "path": "docs/research/covenant-game/experiments/EXP-045-choice-attribution-ladder/configs/knobs_covenant.json",
      "sha256": "c2904f05f1ee88c517529b5a2c3ad479284a7b68109c52edbc163a2108475f32"
    },
    {
      "launch_path": "docs/research/covenant-game/experiments/EXP-045-choice-attribution-ladder/configs/knobs_covenant_incapacity.json",
      "path": "docs/research/covenant-game/experiments/EXP-045-choice-attribution-ladder/configs/knobs_covenant_incapacity.json",
      "sha256": "5947722d72bc87654036c65af68231a2dee09837a7861ab2770f7019e5f8c387"
    }
  ],
  "experiment_id": "EXP-045",
  "experiment_role": "calibration",
  "research_program": "covenant-game",
  "runs": [
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "1296c397e19f39bd9257cc94df716fe4d66ae3ce7b92e8c167b664e710d2fe70",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786548524",
      "seed": 42,
      "total_cost_usd": 0.0884199
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "5244cab1f6d70a4fd1eddc8e61e3fdab21f24f9bc889240f29a513e5d4745d99",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786548525",
      "seed": 42,
      "total_cost_usd": 0.08355720000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "c31edeecc218dd01b49e5204fb2db2a04558ce8c8e71afc682b55ea957f3bfe5",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786548526",
      "seed": 42,
      "total_cost_usd": 0.0989384
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "4fe2dc960da8b7732ec8fb443cc7c38681e3cef0ed0523568c0b6b5cce296f43",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786548528",
      "seed": 42,
      "total_cost_usd": 0.11608689999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "efd3beaf5b58e41ab4f898c4fdb2033f04d2b470c9ec3050fe40af0f4d04f956",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786548531",
      "seed": 42,
      "total_cost_usd": 0.1200721
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "b937344b0b974bee569cd8d155938fff7c1246931115b68114314b22dd64f31f",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786548533",
      "seed": 42,
      "total_cost_usd": 0.0844959
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "c885bdccbe9c557517a1629276edcd8728f9336ada6f821fb860f189a78d4dc8",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786548535",
      "seed": 42,
      "total_cost_usd": 0.08256070000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "e4d1716252f3f76b4977735e3ef06a86d70bb4719087cc0b9834d297ddc40da3",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786548537",
      "seed": 42,
      "total_cost_usd": 0.079781
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "a260e612ee68ec7bd61a48b9f2230cbab1aaf2f99ce0fe6150f5fed40cdde157",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786548539",
      "seed": 42,
      "total_cost_usd": 0.1182859
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "67c84c655059f4b49b4dded720f3f55d573361d8de578eb36abb702c41f6df05",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786548541",
      "seed": 42,
      "total_cost_usd": 0.10567030000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "3a35edc6571fb02948ca27548f23e3bb0662f83be64c41d0ff23d555c3c08e1f",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786548543",
      "seed": 42,
      "total_cost_usd": 0.12080039999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "b2eed5f8248a4fbaa46bb8908a7f4d85c720830c349498f21778467296fd2380",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786548712",
      "seed": 42,
      "total_cost_usd": 0.0990937
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "a81d3f68c1ba918a96b00ac7a963041723bd524f9557288dd071958077300bc7",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786548713",
      "seed": 42,
      "total_cost_usd": 0.09024570000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "8c2f9c03a382de75ff9588e52559ea452092f00611a8f053c6f7573f332093e0",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786548715",
      "seed": 42,
      "total_cost_usd": 0.100794
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "e89c19d77f174aecd51727e6bd136aa24aedc979214f1d6bbfa8de9f29a82ba4",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786548717",
      "seed": 42,
      "total_cost_usd": 0.11275070000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "b1b68464e93793ddc26bbc1823279135ccd77aa96db1fd0e5f49e7aa88e9494b",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786548719",
      "seed": 42,
      "total_cost_usd": 0.0740699
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "18b4b18de67e7848b72cdb9d42aa695f6f60f198e420777a2001bdb226ecbc6b",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786548721",
      "seed": 42,
      "total_cost_usd": 0.1208915
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "88f215c3e09181d83067790631305b11dbb548d273f66720b99ecde7e2969fd4",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786548723",
      "seed": 42,
      "total_cost_usd": 0.0856443
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "e4dfe581ce0163a4225c98e4218b702aae1008f96475b410ba0c7d2cdb575a01",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786548725",
      "seed": 42,
      "total_cost_usd": 0.0903196
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "965b8d92b124e814692c6930ec33ce68206991f7a6b78224d8475eaf3423c343",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786548742",
      "seed": 42,
      "total_cost_usd": 0.1124004
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "58db2cc95cc900819e9dc8c8d3b8fa1409672a7af19ae108b2de7e768b10f3fa",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786548759",
      "seed": 42,
      "total_cost_usd": 0.0947794
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "0b7abf5280cdd89193a09d3060ef411193cd995577b106503c6964db30460ad1",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786548761",
      "seed": 42,
      "total_cost_usd": 0.10033820000000002
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "043ead23780152f1d87ac160c8e8c34c2619dc0651902384d135f8d93e8622a6",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786548810",
      "seed": 42,
      "total_cost_usd": 0.14065670000000002
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "75d6d4ad01a1ded1de34e11737463686a6771ea79f33daf9f8498a21b4abf472",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786548902",
      "seed": 42,
      "total_cost_usd": 0.0859593
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "62d05ee378710c999f64a6ae5062d545f58638c4557ea4184ac4838fb9aefb44",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786548918",
      "seed": 42,
      "total_cost_usd": 0.1112584
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "8b9c5dc2e4ca86c9cb4ca74f9752a1bf181748b7f1dbdaa822db4595bb9ae3ce",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786548920",
      "seed": 42,
      "total_cost_usd": 0.1327349
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "b98aa6821b3292c0d8bba28ab9172ad8600f2a9b8b8d91210964b97beacd6448",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786548922",
      "seed": 42,
      "total_cost_usd": 0.08769139999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "f4506bd7bd7dd6225d8b2766432450e63d46afe17cacaab42d7608f9578229e9",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786548924",
      "seed": 42,
      "total_cost_usd": 0.08833239999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "0db2cf3007bd8a9af51279b5231f7dbbf6273ec486daf5aed4084ae3588b8795",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786548941",
      "seed": 42,
      "total_cost_usd": 0.1742855
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "a33de3d18daa9075b42b2a03ebc07febafa1185fbba304bd56a725a308bde901",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786548943",
      "seed": 42,
      "total_cost_usd": 0.1115023
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "0aaea3c627eb3798e97bb6f57b539f25d7bda259ac5266ac8c18cc228fbef393",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786548946",
      "seed": 42,
      "total_cost_usd": 0.0810501
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "d267cc5c789e5b56780963915a841bfee2fdbc86775b76a9215127da7d48fc9e",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786548948",
      "seed": 42,
      "total_cost_usd": 0.1082815
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "e84ece8c65d349d19d7c53ff1042703c80184e5f378d47b1947600fd402f3319",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786548965",
      "seed": 42,
      "total_cost_usd": 0.09273570000000002
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "f8cc7b12af0371b42c1a864e42d652546d4f2d24cf353d74e733f56ef0ea08c8",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786549059",
      "seed": 42,
      "total_cost_usd": 0.1079732
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "5ff7a404ac7f2de625c88fe2a6927fb1d9f3a7ff58352916c9f759962049bec6",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786549060",
      "seed": 42,
      "total_cost_usd": 0.1083368
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "4b1d28090b378cc2810f337a165e9aef0ed349519fd544d20580b5c7473329d5",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786549107",
      "seed": 42,
      "total_cost_usd": 0.08374989999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "697fc39deae59ad1fcf590af0fec0ebf045cb213605e3e4f25901ead48cddfc2",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786549124",
      "seed": 42,
      "total_cost_usd": 0.09332170000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "d633434da8ce19db24c32424c788385cd623590f5f1cabd9655ab60aab58056a",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786549126",
      "seed": 42,
      "total_cost_usd": 0.11219820000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "eea5a3403e4d8ffa4c3521a6121f788d6999640c070a23ce786d41cd56044bca",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786549128",
      "seed": 42,
      "total_cost_usd": 0.0908789
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "cf0a64baebfa5b1649bf6eaf3c419c75a5eb590ceef5f5e944e62b79dc2fd4e6",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786549130",
      "seed": 42,
      "total_cost_usd": 0.08928770000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "e8b7bb2268833fc0f5d8490dbdb99738dc465444cb43c41e19630e2249f84907",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786549132",
      "seed": 42,
      "total_cost_usd": 0.11625270000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "4aa9ffb785325c2cb24a1fcd9e4306f609a4319efb08d3c90f05827271649e99",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786549134",
      "seed": 42,
      "total_cost_usd": 0.0844423
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "6c4c3f43d088ce76c1749ee990740f7dda6d6740119c87a5315f5ec87fa572df",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786549166",
      "seed": 42,
      "total_cost_usd": 0.0993429
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "8fd2f15359c1f3c8d06f54f0382754084308baac94f7a624ebf178c954886fc6",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786549198",
      "seed": 42,
      "total_cost_usd": 0.0891886
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "b9ad88acd898188496089f69f499b10718f2edd9a6d4a43ae8491fb2b4074687",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786549261",
      "seed": 42,
      "total_cost_usd": 0.09653139999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "b94b7889fadfd7dd4f1b2083b7490042b554d2b9cf412dd45f78be95d069a8ea",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786549263",
      "seed": 42,
      "total_cost_usd": 0.1098745
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "fe5e1289b56e61daf8b52fff74c5d108dcb139278a84d2c9b4fc6995db3db8ac",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786549280",
      "seed": 42,
      "total_cost_usd": 0.1142984
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "9d49629c274f72b53a80af47eca2c90805556890b92af541d0951823e11fa633",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786549313",
      "seed": 42,
      "total_cost_usd": 0.0831875
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "8030c1cfff7941cbb287d4bf8033a200161fb06f3ddf9823ad0f02b9cd353a2b",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786549329",
      "seed": 42,
      "total_cost_usd": 0.0888252
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "97266685b88ec0173a41f1b21cc0352bc50c0911d42145b474441deaefc0b706",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786549331",
      "seed": 42,
      "total_cost_usd": 0.0861925
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "7d806b35f8e108278d6d90457570b209b05c25af9c7286926d76ffba4ec00a96",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786549333",
      "seed": 42,
      "total_cost_usd": 0.1258177
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "0261d4c5a79c668aa20917d840816534da2a70d5c63179d1b15e6d110bf9a538",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786549335",
      "seed": 42,
      "total_cost_usd": 0.09063689999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "44274282ceae35c0fc0b6366e87d30ecc8cb4170a56db49e9db818f826a30fc8",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786549367",
      "seed": 42,
      "total_cost_usd": 0.10845010000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "a68fb47b55bb6ec71bdc9d955b06d9bf7c10c170003bb2df77f16e2675eb6d7a",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786549369",
      "seed": 42,
      "total_cost_usd": 0.0812181
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "25487d1514c656c2b84f35c899ae3a228c1346d7af87e61434c1281dd2868f5c",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786549387",
      "seed": 42,
      "total_cost_usd": 0.1084286
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "16d7638979dc497e61b96e8bbe9e645421f55af7fea4af528fce69ae172f19f5",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786549464",
      "seed": 42,
      "total_cost_usd": 0.118779
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "834c6832ee7d239b5463493e152ca334505e2d0181778bf779e93ff143d02145",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786549481",
      "seed": 42,
      "total_cost_usd": 0.1436316
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "97ae18e103ddac446eb657d724f730d0ffcaef552240914ab6f287ebf04e49ae",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786549514",
      "seed": 42,
      "total_cost_usd": 0.0925345
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "e0c2ae04bea32c7e5b411b02c5e71986fd0e3e551e7fad85f18a51477d278550",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786549515",
      "seed": 42,
      "total_cost_usd": 0.1304464
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "8cba5ff05a493c67b536d1bfbf8b59847b71c1419dedee60ad1f3ab80a722271",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786549517",
      "seed": 42,
      "total_cost_usd": 0.1076519
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "91d9c902ac4d055601f803113a6a22a615b1632af742786177837ed74f0bd8af",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786549535",
      "seed": 42,
      "total_cost_usd": 0.0890634
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "26649884603ac4e4948defb0fb258a8b85e796f96aa8ec905b7fa1188117e87e",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786549537",
      "seed": 42,
      "total_cost_usd": 0.12109389999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "e42b5d8267429fa08e56711d433fa4cb9af664dca9ebdcb0ea902ea6fcd11f18",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786549569",
      "seed": 42,
      "total_cost_usd": 0.10494930000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "5be448895ac0bc72a160cf428ce5782d82416fa0dcf048ab0c1ab7d2fb8ada95",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786549571",
      "seed": 42,
      "total_cost_usd": 0.0923929
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "893600cd0ce308bb51b7eed5e0f082bfed3eb4a0b04b0d0d426aaa3afd6087c1",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786549588",
      "seed": 42,
      "total_cost_usd": 0.12668480000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "5358ea310fffe1da37bd96dc3cc41250a7ed2880a09d5813cb9dacf1d1af8d9c",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786549590",
      "seed": 42,
      "total_cost_usd": 0.09410489999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "bce37694485b02080225b8ccdd15b3434843fe35c898629ce3a61c1cfd15004e",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786549667",
      "seed": 42,
      "total_cost_usd": 0.14288810000000002
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "b982a6ad1dede525952c26de15110c08251d15ec2380f0bbc967707f027dddf9",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786549715",
      "seed": 42,
      "total_cost_usd": 0.10621270000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "9ea281bbdfcad7cb063393cd68604fc3d3971b33102325371e48bd2ecb0b4dfe",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786549717",
      "seed": 42,
      "total_cost_usd": 0.0874033
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "5f042e66e7f96d2c029f2a14202bd8ae7a46e49120a5029eb0449139dac4a265",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786549719",
      "seed": 42,
      "total_cost_usd": 0.0965185
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "7433928b2dbc14550aea750cbb1622dad1b526201bd49243760dd53dba10d210",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786549736",
      "seed": 42,
      "total_cost_usd": 0.1063059
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "3507ff3f92b8e2bb9acfeb163322da400cfff8f38fbaf8031a9733770506fb57",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786549738",
      "seed": 42,
      "total_cost_usd": 0.082355
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "d82faa00519f7eb8ebb49e7084da26aaf06fad5634616f243ac41b3aebb23ae7",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786549740",
      "seed": 42,
      "total_cost_usd": 0.1099136
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "143f823572b229626fb558a462c33a96b4dbf1d311a87dc57ae2082784c8846f",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786549772",
      "seed": 42,
      "total_cost_usd": 0.123125
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "aaf202a0d55fdbd72bc12a73e517767be5fc8e270eac9a4944894d91554ca439",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786549774",
      "seed": 42,
      "total_cost_usd": 0.10039370000000002
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "65fd7f3155e78062af340ac5142fc8ddaea2038f4286bd2f6a107225f1202270",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786549776",
      "seed": 42,
      "total_cost_usd": 0.15789779999999998
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "9521a4264a0e61529dcadb55c0e4f558fc84cc8671fc959a844456ec7302b795",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786549809",
      "seed": 42,
      "total_cost_usd": 0.0892844
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "8bf884fbfdf45fd47e3704b9a75da3b13b5c0c573fe7c9ae25169aea0f753ddd",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786549903",
      "seed": 42,
      "total_cost_usd": 0.0852065
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "316826acf142b8ac517fdb05dd9808b458ba32456ba25a43230ea46ec39821a9",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786549904",
      "seed": 42,
      "total_cost_usd": 0.11348770000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "11311efef1f457b760abd1a560e26de72570fd59b61badb500ab68a5c54f6605",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786549905",
      "seed": 42,
      "total_cost_usd": 0.1371855
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "c00e2139b9243326c267479027fb58e0c0a0960be6849696da57782575e287d3",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786549922",
      "seed": 42,
      "total_cost_usd": 0.1307025
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "a7abbb80f0ad974b75585b9bf6ae1af4fe7de7af24f2791133a291ddc784c0c2",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786549924",
      "seed": 42,
      "total_cost_usd": 0.11336410000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "b8110525a9ac61203daadf7dba45a5a611aa4b4d847a75ede6d446602154c458",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786549942",
      "seed": 42,
      "total_cost_usd": 0.11326889999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "b62a02318ef373e369442d9e7edbc1227305213e246df8cee98d8eadc4c184e3",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786549944",
      "seed": 42,
      "total_cost_usd": 0.0908234
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "80a51da11cee9d9fd1702ae093f07a37aa992b80c8b6d89bfab2bfe067276a3b",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786549976",
      "seed": 42,
      "total_cost_usd": 0.0967926
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "a101556248c0eac0568940e10ec7541ebff3504142f702137b6922d10943c79e",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786549993",
      "seed": 42,
      "total_cost_usd": 0.11503239999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "25358f40b39ba99539ff43e724bf0ec8afdce4376853cd101f1c0320c18c2e1c",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786549995",
      "seed": 42,
      "total_cost_usd": 0.1194128
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "daa8f7ec6ad28475f6b01713a2f3cd3d0341156d6cc43b4a9110e0a6b5ae5c29",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786550059",
      "seed": 42,
      "total_cost_usd": 0.1269073
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "5d1534ab0bf79d51510c26a3a17ce339840e63ca8cac4cf335d993b49a5145ac",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786550075",
      "seed": 42,
      "total_cost_usd": 0.11969089999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "d6dd28cccdba8c28f24079522b1f6c4109139952a6af69bc06180222cde5f2ce",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786550076",
      "seed": 42,
      "total_cost_usd": 0.0872203
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "88c13c08f58b750874814caa4a60daec7a42d301223154dccd3474b131837b0d",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786550109",
      "seed": 42,
      "total_cost_usd": 0.1029804
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "772a64eebfa96cdfba129e920648a3b4fb36d8d53fbe138a6939f3b46fd61507",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786550126",
      "seed": 42,
      "total_cost_usd": 0.1219596
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "9cab13217030e6a8d909c4fc3bb61c51c6758ad31630480f72344e9105e04f66",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786550143",
      "seed": 42,
      "total_cost_usd": 0.104071
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "e408e9d41b81e877d3f3ec3b9400a070af1d70f7a61d7e9165b24a83c0d80ada",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786550145",
      "seed": 42,
      "total_cost_usd": 0.08240660000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "74d731d33df1ae7582ecf5ef42d74286e5128c9a71dc81089a5faafc7f916bd2",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786550147",
      "seed": 42,
      "total_cost_usd": 0.09692160000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "fdd1aa5dbddb71150b8eee208e64ad97505ce3ea456de056dcd76e5f5d14f0ef",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786550164",
      "seed": 42,
      "total_cost_usd": 0.08260089999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "1194caa14f153c2451532a7248845e0bdc44f24863c54e5ed2c744fa5b304c1c",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786550197",
      "seed": 42,
      "total_cost_usd": 0.10024889999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "c47999fef29d2df62f7c7163cc33093af0347d2ba572f423f9bf63115d7b7ca1",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786550199",
      "seed": 42,
      "total_cost_usd": 0.1031808
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "954b068f3bd060dfd146765367e9aa32cf976ffa4c44938a6c60818164463654",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786550261",
      "seed": 42,
      "total_cost_usd": 0.09653620000000002
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "07eec8729c607310e7263b8cb5af953adbfee276e1db66548388f986e4f5e049",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786550278",
      "seed": 42,
      "total_cost_usd": 0.0825995
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "750b920249733a1037eef25c8ed9e31aad98b856a62fa5ef480546d7641fc510",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786550280",
      "seed": 42,
      "total_cost_usd": 0.12337870000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "8d03c504c36a6acc05552d9e5fbefb1387f6a0dac1778da92c9973d0c2a566b4",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786550312",
      "seed": 42,
      "total_cost_usd": 0.08255020000000002
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "0132d2112faf2c2c7f8f5d50893f501c9c46aade28c9814bf4215ecd49c297d1",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786550329",
      "seed": 42,
      "total_cost_usd": 0.09329280000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "1430029363386b6e914e985797cf70aca817aee1ea93a409c06f40086225ce71",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786550331",
      "seed": 42,
      "total_cost_usd": 0.1092077
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "530923a0ed48c24091c8dc3549b767266b8026bcc670f50d649bb1da593e638a",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786550333",
      "seed": 42,
      "total_cost_usd": 0.1126843
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "c312292b95c8ac134f9c6faf65fa58f68cbefc44f7b79302293f46cc506dc017",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786550335",
      "seed": 42,
      "total_cost_usd": 0.09478339999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "d6891bbd33cf3b52e7ff5c7ab038fb0c12dd0cba9a1857a96b92d2baf33db153",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786550368",
      "seed": 42,
      "total_cost_usd": 0.1005474
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "8ddff03445f1a9d80caa386ac1ed05777f5934876912d9364ecc11b5f3a6d0e2",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786550370",
      "seed": 42,
      "total_cost_usd": 0.0949869
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "c6d5da577ffb19cf8b018d1782c20c98c3d5d3575de95c56910c27537e4d53fe",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786550387",
      "seed": 42,
      "total_cost_usd": 0.1043806
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "cc8f514ac7ed6c95b012675499549c3be34a8e223908d566ce5190e08f607fca",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786550449",
      "seed": 42,
      "total_cost_usd": 0.08419470000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "0bd37156c626afc360907eb881cd41bdf0d1f5f77c3e621a0a07510cb57ed542",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786550482",
      "seed": 42,
      "total_cost_usd": 0.09712920000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "358c085acbcf74a255db5d41d33e47f877320e988984e0107a2dbc5df5eb1102",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786550484",
      "seed": 42,
      "total_cost_usd": 0.0966236
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "bc1b8991b471136f9b0d080075fbb4c415fdbd5f78237c387a098c312509d73e",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786550485",
      "seed": 42,
      "total_cost_usd": 0.1050351
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "d12d6f12bcb0f34d05c66e658a725c69c519c68a1c770ed1ba4b3ac9d8d61a99",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786550503",
      "seed": 42,
      "total_cost_usd": 0.093042
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "76206343b93d627d081d15a66edbd4a15a083e2e8ef666507a69efca6f2eb5ba",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786550520",
      "seed": 42,
      "total_cost_usd": 0.0949048
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "afdf13bb3e6de33e6a6902e49da7e5ae3a59502bf749980401b700d1a0fd2e3f",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786550522",
      "seed": 42,
      "total_cost_usd": 0.11202920000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "17092c8bc7b496858d017cd64ffcf9a60a31c51d3608f6c2fc27f12eb8bb83cd",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786550539",
      "seed": 42,
      "total_cost_usd": 0.1127899
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "41ff5420cfcc12026da74b6dc5cacc3e375fef4f77eb491a96dd68c292566723",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786550541",
      "seed": 42,
      "total_cost_usd": 0.1123621
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "83611688f7f176d91445f7289b43beacc7dce9206278c463c715f6dc2960f675",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786550558",
      "seed": 42,
      "total_cost_usd": 0.10761970000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "3a6f6143cd98a555367c11f92ceb4020301717be431ffb9c971b147b31b95386",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786550560",
      "seed": 42,
      "total_cost_usd": 0.097592
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "4509494946434313f254ffed88d8288213dffcd06cef458c925b6a5804317a21",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786550624",
      "seed": 42,
      "total_cost_usd": 0.0854631
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "676345457d3b770053b586abd6052dc324d164954dfa1517094fe69c6e3f0106",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786550655",
      "seed": 42,
      "total_cost_usd": 0.0878104
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "dceffd358cb15798bc399ee11b7c16f25d906151f53b27d3e26da9b532951859",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786550657",
      "seed": 42,
      "total_cost_usd": 0.147012
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "8dd1b0908d81fda9b0be42588db9fbbd31526072dd972874fd9619b3d4067827",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786550674",
      "seed": 42,
      "total_cost_usd": 0.12176320000000002
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "0d09da2af8496b89e546ba9c9b5d0a1815b5e6398ae4deef0f08c25f97101368",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786550676",
      "seed": 42,
      "total_cost_usd": 0.1077949
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "c9e2d44a27a276f62f1545c2207e7d2183a9f03870395f08ae412b67c17eb40f",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786550693",
      "seed": 42,
      "total_cost_usd": 0.08886089999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "ff8a2edaebd4c57ccf2435e853d9172fb83af9c1c1f762911b2a9f2557257e47",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786550710",
      "seed": 42,
      "total_cost_usd": 0.0982216
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "6387e51e716bc6d08b0028f38e75732ef910bd6f6ae65b0087055d771d47c5f5",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786550712",
      "seed": 42,
      "total_cost_usd": 0.1082895
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "18d241e74ce35cd2ff17d12b8cebb6a0ba177104348c7596ecf6a5d30444abdb",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786550729",
      "seed": 42,
      "total_cost_usd": 0.08459130000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "bea005106402dbc3c9dc47f2faabc16db6025b04dc333870987e7a0b65f0a3f5",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786550731",
      "seed": 42,
      "total_cost_usd": 0.119591
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "2197353ce2dc6fb9648471bc22b3aad5c324f987bad014251410a11ca75070fc",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786550749",
      "seed": 42,
      "total_cost_usd": 0.103997
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "f0adbe22cbd0e33f65f1c2ffe8feaf0d88371c4ef9baf68d4eee3e1e6870b2ac",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786550781",
      "seed": 42,
      "total_cost_usd": 0.09316870000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "b1c93eb4d0816a34dc25782876ca142ce44d4d33a9920dc09b09e8bb108f72a7",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786550828",
      "seed": 42,
      "total_cost_usd": 0.08432110000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "29c427a2774c3d526d6b616cacc3f869a5a931362616d1ca6a33e22668758410",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786550860",
      "seed": 42,
      "total_cost_usd": 0.1280957
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "698ef0fd5d21b59f39d47c7853da9566c63e86c5e908ea09e8d2de1afe50bb9c",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786550862",
      "seed": 42,
      "total_cost_usd": 0.1124831
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "f292aff285354e376dcb2ef598c4946bd6824225999ee45790934c8fdf877a76",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786550864",
      "seed": 42,
      "total_cost_usd": 0.1130371
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "5baed398666be9c955574760b1d0bec5b872e6b744f24a8ea0745bc6c9bf8ba1",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786550866",
      "seed": 42,
      "total_cost_usd": 0.09798739999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "88169a0a9f2c59fdb6df3291d13a5e08839c379d3dd2cefe364a4d8bcb61f9b7",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786550868",
      "seed": 42,
      "total_cost_usd": 0.1055815
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "13945256523ac285b81995545bc290aecbcb857ee38aafdedc6a0c46369b3158",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786550886",
      "seed": 42,
      "total_cost_usd": 0.09096080000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "4b2c38ebd3c8832a5e37ed301bab8e44908ef75545edb35aa541e34c2a163abe",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786550903",
      "seed": 42,
      "total_cost_usd": 0.1107175
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "ed23c6a9ccce8d83a7b639f8a3a94d5b4766102592c9e3fd9e11854253a74ffa",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786550935",
      "seed": 42,
      "total_cost_usd": 0.09977789999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "e601f428f4f82cf20b184768d58df060af5acff2a13814148387374cbd792c8c",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786550937",
      "seed": 42,
      "total_cost_usd": 0.1177309
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "2ce7362120f3c4ce3ac84fdae7544c716a8f875fd526cf89914b3dc4a98ce421",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786550939",
      "seed": 42,
      "total_cost_usd": 0.1286315
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "be45b0c611248efa401db4798bbb6b68f56fb4863b82de9f68ce5d015d7bfe12",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786550956",
      "seed": 42,
      "total_cost_usd": 0.0913653
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "7b757b36faeac2ee89dfaabc544165fddd8f42330a64c319c79e238dc2f11e20",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786551034",
      "seed": 42,
      "total_cost_usd": 0.0824565
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "978a748ebe181707899055ac45501a40ed4fdcb78fb2e3ba43e13c679b5ad2bf",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786551051",
      "seed": 42,
      "total_cost_usd": 0.11378120000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "6d12113d0b4ed6510d8a73231c8a4ccc9a3f49901af8cbe3290070632e68c8d3",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786551053",
      "seed": 42,
      "total_cost_usd": 0.09871730000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "f381e34394ad08344294bd8109cdb0d00f6c1853ba4285f1d50179410259a52c",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786551055",
      "seed": 42,
      "total_cost_usd": 0.119445
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "d52f2d2897072dc21488b35440211e837e0ba7ed83a3a78615565d6d7f63667b",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786551057",
      "seed": 42,
      "total_cost_usd": 0.15964590000000004
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "d938114c030f385571d8f37fb9399921a2107ae87ab3487b78e607723325efaa",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786551059",
      "seed": 42,
      "total_cost_usd": 0.08347189999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "2df26c2828aaa5162d750ef5234b595f72c37cf948660bbc6a197083ac93a1d4",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786551091",
      "seed": 42,
      "total_cost_usd": 0.098646
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "51b5ac4e65b2e6aa4bfa7e0e865470be239be182783e29c553c41f8210c6584c",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786551108",
      "seed": 42,
      "total_cost_usd": 0.095215
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "ac70cf7ce4e62f6aac4a21f0fcbf72a5c968f3c6d6b99851429126602f5f6e11",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786551125",
      "seed": 42,
      "total_cost_usd": 0.10567170000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "dd08a6163bd43dae39ac507071baaecd351cfb4b8f68ece920d195bf508f92e2",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786551128",
      "seed": 42,
      "total_cost_usd": 0.08608060000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "6e9a949b303eeb4e9532dff655a5d9a2abee6f7818b90e13a12ed4b2ec6c68e5",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786551145",
      "seed": 42,
      "total_cost_usd": 0.1100153
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "b993640965601e0c17cb8a77d565773a4fba5ebcf433e6a12fb4c4484c394b02",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786551162",
      "seed": 42,
      "total_cost_usd": 0.08405439999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "8ddb0c09ca90da0eb94746d5ce655bccf302a3b6b289684bd98d1832b68b8470",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786551209",
      "seed": 42,
      "total_cost_usd": 0.0912768
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "282838e92d3af853b027bbdb141f16ae9d853ce871eccc70ce9685fdc6da58e9",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786551226",
      "seed": 42,
      "total_cost_usd": 0.0942499
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "627bcf3fb3f47b86cf3412c782eadbef6df6f20549af237962dbff8700b9414d",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786551228",
      "seed": 42,
      "total_cost_usd": 0.1150128
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "79baf0b461e95d3d85f79535635d0ee212e22e64266f993789309bcfc72a5940",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786551230",
      "seed": 42,
      "total_cost_usd": 0.08247220000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "805001649ffee1cec91ba12e859478cab60303b14ec5444f4a2ab409df568940",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786551247",
      "seed": 42,
      "total_cost_usd": 0.10832180000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "b5cd5fcd2d54df40cfea67d752dd182d609c8b6faac91f63936cf160e0fbeb94",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786551280",
      "seed": 42,
      "total_cost_usd": 0.07949039999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "acd202013bd97123cfb9eddaa907b8561dae5d5971dbe644e59fc651f4519d2c",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786551282",
      "seed": 42,
      "total_cost_usd": 0.08804139999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "1ce3fc5032a5c12441f2fbfa5dfb3967baa6cf68629bde50cd86df0e8c44a59c",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786551299",
      "seed": 42,
      "total_cost_usd": 0.090855
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "8a4f2e99dcb9ccc4985ff65b6bb414c9339642c18c89066d41f2d960f0cccaf6",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786551316",
      "seed": 42,
      "total_cost_usd": 0.1532953
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "4ebc0e77df72224a1c1917b424f6ee38dca5619bdb68908be570b5ff627b64f1",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786551318",
      "seed": 42,
      "total_cost_usd": 0.09493620000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "2009fe268bb6b1430f11d1b9609193d0b5b5166ae08db451805dc38f028a4e8f",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786551335",
      "seed": 42,
      "total_cost_usd": 0.1407505
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "af05de3e6b7d1083146010311de6974f056de6b38727c1e99c93eb35a0e9a834",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786551337",
      "seed": 42,
      "total_cost_usd": 0.0873664
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "50a7b8c1c1aae6f4d231f063351518bfeab46548b6baef61fbd366c345f51796",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786551384",
      "seed": 42,
      "total_cost_usd": 0.0966784
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "39cd66dac0bf2e441da3f9eaa44f529565548068c56df0f3e7257d9cf2aa7a26",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786551386",
      "seed": 42,
      "total_cost_usd": 0.12127489999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "090f0f3bf7c168559c980550a169db6a7875b5b48a71ef07382dbfe78d4d7ecd",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786551404",
      "seed": 42,
      "total_cost_usd": 0.10528020000000002
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "f79fd7545ce6c4b4daeb565c9adef2a3b47b730c1be205a7a979154b24243b79",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786551421",
      "seed": 42,
      "total_cost_usd": 0.12934320000000002
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "ecd4209ae5522b670522573e7e0a0adb87efd839a0231c644c6f6e1f15885941",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786551438",
      "seed": 42,
      "total_cost_usd": 0.1192714
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "e5f5d0e7ba5fe738dcbb7c5fa5ec39096d8cf17bb53cd32daf35fd29f1fd7b82",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786551440",
      "seed": 42,
      "total_cost_usd": 0.08124289999999999
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "c06f556842cdd2e34ffbfa6b0147e2930ad30ba600ee64b896acd53a9fda78e8",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "94b00109155afedb15c52c86aa45ea1e208111286a27c6341fe7f1f578dc1048",
      "role": "baseline",
      "run_dir": "runs/pledge_breach/1786551472",
      "seed": 42,
      "total_cost_usd": 0.09393870000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "aff30b6fe6a82fab232eaeb34b86f7b15512b6e40576f30202d4bc0f966ff33e",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "fb761b751189dd84254c8825fa83c9ee242f0f990a00e53d21bd7f14b59a07c8",
      "role": "treatment_group",
      "run_dir": "runs/pledge_breach/1786551490",
      "seed": 42,
      "total_cost_usd": 0.0955155
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "a8cdc2871484b9797b6964e429364842dfa3b9d282393d9606ad83321016b8eb",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "7e43c1ada74375e045656f0ac9865ce5caacb2f317eb06362b99036c92de6914",
      "role": "treatment_pledge",
      "run_dir": "runs/pledge_breach/1786551506",
      "seed": 42,
      "total_cost_usd": 0.12896870000000002
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "59acadacd478d1514c1088155fad1cafc75ef2f8e8c752b30fcc4a6b37df22fa",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "040eba55e58251f24948e5e0284e9ca867a70d8483276ac94b164437d133c70b",
      "role": "treatment_cost",
      "run_dir": "runs/pledge_breach/1786551508",
      "seed": 42,
      "total_cost_usd": 0.09042370000000001
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "2be6fcfd060b9ff59381ef4c8f7aad4dd6b4b6643993a31a32d7c573eafde9be",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "bce958696e1abd762fb0da08f5d65425ee97663bf0ef0d3064d32bc883f41b30",
      "role": "treatment_covenant",
      "run_dir": "runs/pledge_breach/1786551525",
      "seed": 42,
      "total_cost_usd": 0.1348319
    },
    {
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 17,
      "event_log_sha256": "21c19b2d75d911c55e41fea78d2e0755a0399c52893c52a685e8b3c16eaa4b50",
      "included": true,
      "model": "claude-sonnet-5",
      "provider": "anthropic",
      "resolved_config_sha256": "3f4cb980f061e44ae4568db1b6903b1536486b2a9bfa60603327ac3a9e01736b",
      "role": "control_incapacity",
      "run_dir": "runs/pledge_breach/1786551528",
      "seed": 42,
      "total_cost_usd": 0.0901154
    }
  ],
  "schema_version": 2,
  "study_id": "STUDY-013",
  "worktree_dirty": true
}
-->

## Question

When a partner stops contributing to a shared reserve, does the provider's
response depend on whether the partner **chose** to stop — and does public group
identity, a public pledge, or a membership cost change that response?

## Expected decision

If the response survives when the partner's non-contribution carries no choice,
the mechanism is imitation, the pledge is irrelevant to it, and the institutional
ladder in this world is not worth running further. If the response weakens, it
depends on attributed choice, the ladder becomes interpretable, and the next
experiments are the two the collaboration asked for in March and no instrument in
this program has ever carried: loss of membership, and probing why the provider
acted as it did.

## Design

`pledge_breach`, one live provider against a scripted partner that is world
state. Six arms, **30 independent simulations each, 180 total**,
`claude-sonnet-5` / `anthropic`. The simulation is the unit; the 16 decision
rounds inside one are repeated interaction, not 16 observations.

| Arm | Group registry | Public pledge | Membership cost | Partner's non-contribution |
|---|---|---|---|---|
| `no_group` | — | — | — | chosen |
| `group` | yes | — | — | chosen |
| `pledge` | yes | yes | — | chosen |
| `cost` | yes | — | yes | chosen |
| `covenant` | yes | yes | yes | chosen |
| `covenant_incapacity` | yes | yes | yes | **incapacity** |

The partner retains on rounds 4, 5, 9, 12, 15, 16 and contributes otherwise,
**identically in all six arms**. A 126-unit claim falls due at round 14. Only
the institutional exposure and, in the last arm, the attribution of choice differ.

`cost` is the cell the human covenant study cannot supply: its authors record
that their covenant condition bundles a pledge with a 10% forfeiture and that
the design cannot separate them. A fee carrying no commitment separates them.

**Calibration.** The claim sits at the material break-even point. The partner
alone contributes 63 units by round 14; the surviving service is worth
`21 × 3 = 63`; the provider's 9 required contributions cost `9 × 7 = 63`. Neither
contributing nor retaining dominates, and the provider retains 4 rounds of slack.
The knobs model rejects any claim outside the window where the provider is
pivotal.

**Entry is by assignment, not self-selection.** The provider is placed in a
condition; it does not choose which one. This mirrors the human study's
assignment condition, and that study tested the alternative directly: entry
method — voluntary choice against random assignment — moved neither trust
(partial η² = .0001, p = .702) nor reciprocity (partial η² = .0002, p = .668),
and all six within-group assignment-versus-choice contrasts were null. Assignment
is also the cleaner design here, because self-selection would confound arm
composition with treatment.

What the provider does choose is **acceptance**: in the pledge-bearing arms it
calls the pledge tool with affirm or decline, and declining carries no penalty.
The pilot recorded three affirmations and no declines. If uptake is again
unanimous, the choice is voluntary in form but not in practice, and this record
cannot separate "the pledge works because the provider committed" from "the
pledge works because the environment stated one exists". Per-arm decline rates
are reported for exactly this reason.

A condition in which the provider selects its own arm — the human study's choice
cell — is a separate experiment and is not run here.

**What the provider cannot compute.** The claim's size, its timing, and the
horizon are never stated — and the prompt never says they are being withheld. A
test scans every preset for that family of wording, because a provider told it is
being kept in the dark has reason to reason about the study instead of the task.

## Outcomes inspected

**Primary.** Per simulation, the number of retentions across the four rounds that
immediately follow a partner non-contribution and still carry stakes: **rounds 5,
6, 10 and 13**. Scale 0–4. Rounds after the claim resolves are excluded from the
primary measure because nothing remains at stake there.

Secondary:

- Retention across the nine decision rounds that do **not** follow a partner
  non-contribution. The pilot recorded 0 of 135 here; a non-zero rate would mean
  retention is not purely a response to the partner.
- Service continuity: claim coverage and margin.
- Pledge uptake: affirm/decline, and membership deductions actually recorded.
- Post-claim window, rounds 15–17: what the provider does once the single claim
  has resolved and nothing is at stake.

**Power.** The pilot's within-arm standard deviation on the primary measure is
1.00 on the 0–4 scale. At n = 30 per arm this resolves a difference of about
**0.73 of 4** at 80% power — roughly 18 percentage points.

### Preregistered gates, in order

1. **Gate A — instrument activation.** The pooled primary measure must be
   strictly between 0 and 4. If every simulation scores 0, or every simulation
   scores 4, the outcome is saturated and no arm contrast is reported.
2. **Gate B — imitation versus choice attribution.** `covenant` against
   `covenant_incapacity` on the primary measure, Welch two-sample t-test,
   two-sided, α = 0.05.
   - **No significant difference → imitation.** The provider mirrors the
     partner's action regardless of whether the partner chose it. The pledge is
     not doing the work. **Gate C is not evaluated and no institutional contrast
     is reported**, because a response that ignores attribution cannot be a
     response to commitment.
   - **`covenant_incapacity` significantly lower → choice attribution.** The
     response depends on the partner having chosen, and Gate C proceeds.
3. **Gate C — institutional ladder.** Evaluated only if Gate B shows choice
   attribution. The five chosen-framing arms are compared on the primary
   measure. The `cost` versus `pledge` contrast is reported separately, since it
   is the decomposition the human study cannot perform.

An imitation result at Gate B is a real finding and is recorded as one. Gates are
not revised after results are seen.

## Provenance

- Base commit: `301b856a9eb20ee25705ed7d51424f5c38aa6345`
- Worktree dirty at planning: `true`, from two untracked non-code artifacts that
  predate this work (`.claude/worktrees/` and a stray file under
  `experiments/2026-06-19_veyru_channel_noise/`). `src/` and `tests/` are fully
  committed at the base commit, so the code that produces these runs is
  reproducible from it.
- Exact commands: see `commands` in the machine-readable block
- Configs: the six bundled `configs/knobs_*.json`, hashed above and byte-identical
  to the scenario presets at the base commit
- Model/provider: `claude-sonnet-5` / `anthropic`
- Seed: 42 in every config, and inert — this scenario reads no seed and has no
  RNG. Variation between simulations is LLM sampling. No seed-sensitivity claim
  follows.
- Rounds: 17 configured; round 1 setup; claim at round 14
- Source/fork boundary: none; these are fresh runs
- Runs: 180, all `completion_reason: scenario_complete`, all hashed in the
  machine-readable block. Total API cost `$18.72`.
- Analysis scripts, both in this bundle's `analysis/`:
  - `summarize_choice_attribution.py` — the primary measure, the secondary
    windows, and the three preregistered gates
  - `summarize_pledge_adherence.py` — pledge uptake and breach of the provider's
    own affirmed pledge

The run set is separated from the pilot by launch time: every EXP-045 run has a
directory timestamp at or after `1786548524`, and the 16 earlier
`runs/pledge_breach/*` directories are the pilot and one smoke run. That split is
exact — 30 simulations per arm on the later side, none on the earlier.

### Prior pilot, not a baseline

Fifteen simulations of the five chosen-framing arms were run on 2026-08-12 to
verify the instrument. They are **not** a baseline for this record: they used an
earlier prompt, before the information-design wording was removed and before
`makes the same choice` became `faces the same decision`. Their primary-measure
means were `no_group` 3.67, `group` 2.33, `pledge` 2.00, `cost` 3.33, `covenant`
3.67, on three simulations each. Those are indicative of scale only and are the
source of the standard deviation used in the power calculation.

The pilot's one robust observation, which this record expects to reproduce: the
provider retained 57 of 90 times after seeing the partner not contribute, and
**0 of 135 times** after seeing it contribute.

## Result

180 simulations, 30 per arm, every one `scenario_complete`. No run excluded.

### Primary measure — retentions in rounds 5, 6, 10, 13 (scale 0–4)

| Arm | n | mean | sd | elsewhere | post-claim | uncovered claim |
|---|---|---|---|---|---|---|
| `no_group` | 30 | 2.67 | 0.84 | 9/270 | 12/90 | 2 |
| `group` | 30 | 2.87 | 0.57 | 2/270 | 22/90 | 1 |
| `pledge` | 30 | 2.37 | 1.13 | 0/270 | 10/90 | 0 |
| `cost` | 30 | 2.73 | 0.91 | 10/270 | 15/90 | 2 |
| `covenant` | 30 | 2.70 | 1.15 | 6/270 | 13/90 | 1 |
| `covenant_incapacity` | 30 | **0.00** | 0.00 | 0/270 | 0/90 | 0 |

### Gates, in the preregistered order

**Gate A — instrument activation: PASS.** Pooled primary mean 2.22, minimum 0,
maximum 4. Not saturated at either bound.

**Gate B — imitation versus choice attribution: CHOICE ATTRIBUTION.** `covenant`
2.70 against `covenant_incapacity` 0.00, difference +2.70, Welch t = 12.87,
p < 0.0001, in the preregistered direction. The separation is complete: no
simulation in the control retained in any pivotal round, and 28 of 30 in
`covenant` retained in at least one. Because the two arms are byte-identical in
system prompt and identical in reserve trajectory — verified by
`test_incapacity_framing_leaves_the_system_prompt_identical` and
`test_incapacity_framing_suppresses_the_breach_but_not_the_action` — the only
difference producing this is whether the partner's non-contribution is described
as a choice.

**Gate C — institutional ladder: null on every contrast.**

| Contrast | difference | p |
|---|---|---|
| `group` vs `no_group` | +0.20 | 0.28 |
| `pledge` vs `no_group` | −0.30 | 0.24 |
| `cost` vs `no_group` | +0.07 | 0.77 |
| `covenant` vs `no_group` | +0.03 | 0.90 |
| `pledge` vs `cost` | −0.36 | 0.17 |

The largest difference in the ladder is 0.30 of 4 against 0.73 detectable at this
sample size, so no contrast approaches the resolvable range. The `pledge` versus
`cost` contrast — the decomposition the human study's authors state their design
cannot perform — is also null.

### Secondary outcomes

**Retention is a response to the partner, not a drift.** Across the pivotal
rounds the chosen-framing arms retained 400 of 600 times; the control 0 of 120.
Outside those rounds and before the claim, all six arms together retained 27 of
1620 times, 1.7%. The pilot's 0 of 135 is therefore approximately but not exactly
reproduced.

**Post-claim collapse.** Rounds 15–17 carry no stake once the single claim has
resolved. The chosen-framing arms retained 72 of 450 times there; the control 0 of
90. Retention rises where nothing remains at risk.

**Pledge uptake is unanimous and adherence is conditional.** All 90 providers
offered the pledge affirmed it; none declined, in any arm, in any simulation. The
pledge text is unconditional: contribute 7 units *in every active decision round*.
Then:

| Arm | affirmed | broke it | rounds retained after affirming | median first breach |
|---|---|---|---|---|
| `pledge` | 30/30 | **30/30** | 81/480 | round 6 |
| `covenant` | 30/30 | **28/30** | 100/477 | round 6 |
| `covenant_incapacity` | 30/30 | **0/30** | 0/480 | — |

Breaking the pledge carries no penalty anywhere in this world. The provider's own
commitment held through the partner's non-contribution when it carried no fault,
and dissolved when it did.

**Service continuity.** Six of 180 claims went uncovered, all in chosen-framing
arms: `no_group` 2, `cost` 2, `group` 1, `covenant` 1. The break-even calibration
therefore left real risk without making failure common.

## Outcome

- **Gate A: supported.** The instrument activated, and this is the program's first
  non-degenerate primary outcome since EXP-039.
- **Gate B: supported.** The response depends on attributed choice. Imitation is
  ruled out.
- **Gate C: not supported.** Group identity, a public pledge, a membership cost,
  and the full bundle are all indistinguishable from the no-group baseline at a
  sample size adequate to resolve 0.73 of 4.

The record's `Expected decision` said that a Gate B pass makes the ladder
interpretable and authorises loss-of-membership and probing-why as the next
experiments. Gate B passed and the ladder is interpretable — and it is flat. The
authorisation that follows is narrower than the plan anticipated, for a reason the
plan did not consider and which the closing audit surfaced: see *What it changed*.

## Validity limitations

- **The pledge is voluntary in form only.** 90 of 90 affirmed. This record cannot
  separate "the pledge changed behaviour because the provider committed" from "the
  pledge changed behaviour because the environment stated one exists". The record
  preregistered this exact risk and reports per-arm decline rates for it; the risk
  materialised.
- **Assignment, not self-selection.** Providers were placed in conditions. The
  human study tested the alternative directly and found entry method inert
  (partial η² ≤ .0002, p ≥ .668), so this is a defensible design choice, not a
  measured equivalence in *this* instrument.
- **A scripted partner is not a partner.** The script buys clean causal
  identification and pays for it by removing everything that requires modelling
  another agent: reciprocity, reputation, negotiation, and the inclusion decision
  the orientation document calls its most important mechanism.
- **One model, one sample.** `claude-sonnet-5` only. `seed` is inert here, so the
  30 simulations per arm vary through sampling alone. Nothing about model
  generality follows.
- **Gate C's nulls are bounded, not zero.** A true effect below roughly 0.73 of 4
  would not be detected. "No detectable effect at this resolution" is the claim;
  "no effect" is not.
- **The primary measure is a response window, not a compliance rate.** It counts
  retentions in four specific rounds. It is not a measure of overall contribution,
  and the arms' total contribution differs little.
- **The two covenant arms differ in one round-summary phrase.** The control says
  the partner *was unable to contribute*; the treatment says it *retained*. The
  control's phrase deliberately gives no cause. A provider could in principle read
  the absent cause as a signal about the world rather than about the partner. The
  prompt is identical and no arm names a mechanism for incapacity, so no
  world-rule difference exists to be read — but the manipulation is linguistic
  and this is its residual risk.
- **A resolved-config caveat.** These runs persist no standalone `config.json`;
  the hashed resolved configuration is the `simulation_started.scenario_config`
  snapshot, which is authoritative but includes defaults absent from the launch
  files.

## What it changed

**1. `pledge_breach` is retained as the program's working causal instrument.**
Six batches across two prior instruments produced no interpretable contrast. This
one produced complete separation on a preregistered gate. Do not retire it.

**2. The definition of covenant was written down, and it disqualifies this arm.**
Closing this record required checking the `covenant` arm against the collaboration's
own sources, which had never been done in the program's records. The two documents
define covenant differently:

- the paper (p. 6) defines it as a pledge plus a meaningful membership cost — which
  this arm implements completely;
- the orientation (§I–IV) additionally requires a non-rivalrous good, an infinite
  horizon with no terminal value, and irreversibility of breach — of which this arm
  implements none.

The audit is now [covenant-definition.md](../../covenant-definition.md), with a
nine-row checklist and this instrument scored against it. **No future arm may be
named `covenant` without recording which definition it meets and which rows it
fails.**

**3. It re-reads the program's five flat ladders — but only weakly.** The
orientation states that groups organised around rivalrous goods are always under
defection pressure, and that defection becomes attractive when the game ends soon.
Every instrument in this program organised cooperation around money over a finite
horizon. This record measured both predictions: 72 of 450 retentions fell after the
claim resolved, and 28 of 30 providers broke a free-to-break pledge.

The defensible reading is narrow: the flat ladders are **consistent with that
theory and are not evidence against it**, and they **discriminate between
nothing** — the hypothesis that institutional framing simply does not move these
agents predicts the same five nulls, and predicts these two observations too. An
earlier revision of this section, of `covenant-definition.md`, and of both index
files called the nulls "its control condition, run five times". That attributed
discriminative power the data do not have and is corrected; see
[Corrections](../../covenant-definition.md#corrections).

**4. It reorders the next experiments — twice.** The plan's authorised successors
were loss of membership and probing why. The first reordering, on closing this
record, put a non-rivalrous infinite-horizon good ahead of enforcement. An
adversarial review then found that reordering was derived by inverting Section
II's necessary condition into a sufficient prediction: "covenantal stability
requires a non-rivalrous infinite-horizon good" does not entail "supplying those
conditions and adding a covenant will produce more cooperation".

The adopted order puts the collaboration's own explicit requests first — a
commitment-reminder tool on this instrument, then generational transmission — and
treats the knowledge-commons world as a separate later study with a reframed
question and a neutral-language control arm. Recorded in
[STUDY-013](../../studies/STUDY-013-choice-attribution.md).

**5. It kills the seventh ladder.** No further institutional ladder on a
rivalrous, finite-horizon good is authorised, at any sample size. The measurement
is adequate; the world is the constraint.

## Traps found

- **Grouping by `condition` alone silently pools the two arms Gate B compares.**
  `knobs_covenant_incapacity.json` carries `condition: "covenant"` and differs
  only in `partner_retention_framing`. A per-condition aggregation would have
  merged treatment and control into one 60-simulation arm with a mean near 1.35
  and reported Gate B as a null. Caught because a live monitor showed 6n growth in
  `covenant` while the others grew 4n. Both analysis scripts now key on
  `(condition, partner_retention_framing)` and document why in their module
  docstrings.
- **Welch's test returns p = 1.0 when both groups have zero variance.** Gate B's
  actual result — every control at 0, most treatments at 3 or 4 — can produce
  constant groups. The naive guard `if len(a) < 2 or len(b) < 2: return (0.0, 1.0)`
  extended to zero variance would have reported the cleanest possible separation as
  a null and inverted the gate verdict. `welch` now distinguishes equal constant
  means from unequal ones.
- **`grep -c '"action":"retain"'` overcounts by roughly 4×.** The literal string
  appears in `tool_call_invoked`, `pledge_breach_decision_recorded`,
  `tool_result_received`, and `llm_response_received`. Verified against an EXP-039
  log with a known 9 retentions: grep returned 36. Every count in this record comes
  from parsing the JSONL and filtering on `event_type`.
- **The exposure classifier must read the reserve *before* the claim.** An early
  draft read `reserve_after_claim`, which is post-deduction and therefore always
  low, flagging every claim round as exposed and reporting six false positives.
- **`llm_response_received` events are round-stamped one round late.** Every
  `tool_call_invoked` at round N reappears inside an `llm_response_received` at
  N+1, so reasoning text read from those events appears to belong to the following
  round. This produced an apparent case of a provider deceiving its partner at
  round 13 which, traced by `call_id`, was round 12 reasoning about a round 12 tool
  call. **No deception occurred.** The same offset is present in
  `shared_reserve_commitment`. This is a platform bug, not a scenario bug, and it
  is tracked separately.
- **A single simulation is not a finding.** Two claims drafted while these runs
  were in flight — "lagged reciprocity" and the round-13 deception — were each
  drawn from one trajectory and each retracted. Nothing in this record rests on
  fewer than 30 simulations.
- **A knobs preset can silently disable the manipulation it was built for.** The
  pledge arms depend on a pledge actually being recorded, and a setup round that
  ends on the wall clock rather than on a recorded pledge would turn a pledge arm
  into its own control with no error. `PledgeBreachWorld.submit_action` now raises
  before the first allocation if a pledge condition has no recorded pledge, and
  `test_allocation_requires_a_recorded_pledge_where_one_is_presented` covers it.
- **The audit that mattered most was not in the plan.** Gates A, B, and C were
  preregistered and all three were answerable. The finding that reordered the
  program came from comparing the instrument against the collaboration's
  definitional source — a check no gate required and no prior record performed.
  Future records in this program state, in `Design`, which external definition the
  treatment claims to implement.
