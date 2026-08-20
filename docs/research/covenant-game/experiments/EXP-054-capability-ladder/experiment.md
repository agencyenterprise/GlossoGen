# EXP-054 — Capability ladder within one stack: `gpt-5.6-luna` and `gpt-5.6-terra` against `gpt-5.6-sol`

**Status:** complete
**Date opened:** 2026-08-19
**Date closed:** 2026-08-19
**Research program:** covenant-game
**Study:** STUDY-015 — Informational versus dispositional failure at the frontier
**Role:** ablation

<!-- experiment-record:v2
{
  "base_commit": "0c2f6a7255a34783b5007d99539f022ec179cb72",
  "commands": [
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run repo_stewardship --model gpt-5.6-terra --provider openai --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-054-capability-ladder/configs/baseline-resolved.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run repo_stewardship --model gpt-5.6-terra --provider openai --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-054-capability-ladder/configs/rule-resolved.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run repo_stewardship --model gpt-5.6-terra --provider openai --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-054-capability-ladder/configs/covenant-resolved.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run repo_stewardship --model gpt-5.6-luna --provider openai --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-054-capability-ladder/configs/baseline-resolved.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run repo_stewardship --model gpt-5.6-luna --provider openai --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-054-capability-ladder/configs/rule-resolved.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run repo_stewardship --model gpt-5.6-luna --provider openai --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-054-capability-ladder/configs/covenant-resolved.json"
  ],
  "configs": [
    {
      "launch_path": "docs/research/covenant-game/experiments/EXP-054-capability-ladder/configs/baseline-resolved.json",
      "path": "docs/research/covenant-game/experiments/EXP-054-capability-ladder/configs/baseline-resolved.json",
      "sha256": "c4f70183abd2002d277d9b09c4f37f3db0fd3ab0ea71b735a83d732ace9e2aab"
    },
    {
      "launch_path": "docs/research/covenant-game/experiments/EXP-054-capability-ladder/configs/rule-resolved.json",
      "path": "docs/research/covenant-game/experiments/EXP-054-capability-ladder/configs/rule-resolved.json",
      "sha256": "699416525e7d2b922cff88dcd83a86c0f5164f6d21a3e68adaa6d5cc2c889579"
    },
    {
      "launch_path": "docs/research/covenant-game/experiments/EXP-054-capability-ladder/configs/covenant-resolved.json",
      "path": "docs/research/covenant-game/experiments/EXP-054-capability-ladder/configs/covenant-resolved.json",
      "sha256": "4f1cfb838b3b7cfb7c8c5e819373e732da093244aca8ce94c1e6e7c09982898b"
    }
  ],
  "experiment_id": "EXP-054",
  "experiment_role": "ablation",
  "research_program": "covenant-game",
  "runs": [
    {
      "completed": true,
      "event_log_sha256": "4f8a3d9dc7d8180371a95f6ef9a8b3c18989369a14e36bac92cd7a7c03e747df",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185089",
      "total_cost_usd": 0.02833116
    },
    {
      "completed": true,
      "event_log_sha256": "c709379f21d45ddf1a74015be5bc6880c3b08231be2059f62ac2d1d55c358502",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185099",
      "total_cost_usd": 0.0228545
    },
    {
      "completed": true,
      "event_log_sha256": "1795624e7ed9cf46fce85d2353fd32f2e023949d99f50f4fb527650bac768698",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185108",
      "total_cost_usd": 0.025353140000000003
    },
    {
      "completed": true,
      "event_log_sha256": "73165409ca9229d3d3909cb577df976e72117593a0b66274f308b78fd610189e",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185120",
      "total_cost_usd": 0.02799696
    },
    {
      "completed": true,
      "event_log_sha256": "cc6fdec1b47a13deed4b15968e3b0508a3b2d759e0a3bce0f6d930ba4416b7c1",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185288",
      "total_cost_usd": 0.026066119999999998
    },
    {
      "completed": true,
      "event_log_sha256": "b32fbc93e1356551e28d1ffc5135921aad899be6fd994a11a5491fbb7c859fa8",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185297",
      "total_cost_usd": 0.03213216
    },
    {
      "completed": true,
      "event_log_sha256": "3d21f14a927004752ecc42d25880e9173111715579be68d03aaec5d93f6b2d86",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185325",
      "total_cost_usd": 0.029210180000000002
    },
    {
      "completed": true,
      "event_log_sha256": "d66aec7f8d3a3ea70c7b09a3ad15729e611206f8c1a526a70e5312e4b02922dd",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185454",
      "total_cost_usd": 0.025369460000000003
    },
    {
      "completed": true,
      "event_log_sha256": "c3eef1cd87e543a489174773f9cac3de245543f25b3f9fc4fc6cc3b015eba625",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185504",
      "total_cost_usd": 0.0264298
    },
    {
      "completed": true,
      "event_log_sha256": "a9cebb8b52bb1013c3c79808825d7dc047a9c62e02c93541a32eaa9bdb2fe905",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185533",
      "total_cost_usd": 0.02579468
    },
    {
      "completed": true,
      "event_log_sha256": "4b7a6e5cefa7f398dcb382b46ceb0f2f93a57639b36c020129ab7fee103bba23",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185094",
      "total_cost_usd": 0.42341275
    },
    {
      "completed": true,
      "event_log_sha256": "bdb1d963fb8dfd3f161165da4557b6e2eab4359e8d5da6989824953dec4388aa",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185100",
      "total_cost_usd": 0.40607175
    },
    {
      "completed": true,
      "event_log_sha256": "fd1210e1c1cf7ac69c97e70513dbf465df9b6378e7248d78ab63db5eacb61591",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185110",
      "total_cost_usd": 0.43530274999999996
    },
    {
      "completed": true,
      "event_log_sha256": "d86b200f83089fea76942c0f6a5a51b64287fba0fc73d5b2a14393168d43a09a",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185119",
      "total_cost_usd": 0.40979224999999997
    },
    {
      "completed": true,
      "event_log_sha256": "24a05ac8fc517f8a7e436d581b00f0d31e4d569c10702d4e290568856d46f43d",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185287",
      "total_cost_usd": 0.4456685
    },
    {
      "completed": true,
      "event_log_sha256": "09e126f7f0ced2637eb51be3885dc3fec752fe60fe163f103bbbacc41479eb57",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185296",
      "total_cost_usd": 0.462908
    },
    {
      "completed": true,
      "event_log_sha256": "ed1598ec136c53874f98f3190cb6556e0b8c917c760e5bddc567878580dd513a",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185305",
      "total_cost_usd": 0.31471675
    },
    {
      "completed": true,
      "event_log_sha256": "abbcf172e75d9815a57edf5eb50245c6743fd9bc15af94f7bd6dc6db892e8912",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185474",
      "total_cost_usd": 0.4405015
    },
    {
      "completed": true,
      "event_log_sha256": "ceab56a3f44f9c00e1c1e4b5c386c36e26a7091598f57d30bc6cf921a66e6c2e",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185483",
      "total_cost_usd": 0.34240225
    },
    {
      "completed": true,
      "event_log_sha256": "a978a3709567a30a1dba2c8d291c856a1f5d9f1ad18a411f8eca03ece227c6e7",
      "included": true,
      "resolved_config_sha256": "f9452c520e563fececa0886b71fedfe33b580bf7f4a69a5a1f199507617559f5",
      "role": "control:baseline:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185534",
      "total_cost_usd": 0.36296425
    },
    {
      "completed": true,
      "event_log_sha256": "e076543043f073553d0ccd5a733b424662b0497d312e7e08128d03bdb97d1e17",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185096",
      "total_cost_usd": 0.04007258
    },
    {
      "completed": true,
      "event_log_sha256": "c98abeb63a09ea977eb811791263eef3986077f4d45156d4b49180b103344746",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185107",
      "total_cost_usd": 0.04118474
    },
    {
      "completed": true,
      "event_log_sha256": "22a716671dfe46dbae81d57315c64880baa93b2f72f3d93715e93ffb2efec20a",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185117",
      "total_cost_usd": 0.03326326
    },
    {
      "completed": true,
      "event_log_sha256": "7d38e29aef0bbf6366260bacda8cee9a4bb6d321bc63e3488866a40c0abdf819",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185285",
      "total_cost_usd": 0.05178174
    },
    {
      "completed": true,
      "event_log_sha256": "41db9c392a8612098086062acf0eeabf5745815927f66e64e11711251f25aa53",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185293",
      "total_cost_usd": 0.044080839999999996
    },
    {
      "completed": true,
      "event_log_sha256": "6f1a6a0706973048db512d4993e2c5d5d7b4cd22f5fc6c79d1d5adfd2b9d1847",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185302",
      "total_cost_usd": 0.0275675
    },
    {
      "completed": true,
      "event_log_sha256": "95f2de4002500507a0cbaf67ceb8c778c20172992a19317d4a5a24e134ccf328",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185451",
      "total_cost_usd": 0.04361266
    },
    {
      "completed": true,
      "event_log_sha256": "20113b2deef825503b46d019a54961227b6c1498516584f6756fbbd3d5ad76a5",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185501",
      "total_cost_usd": 0.035855479999999995
    },
    {
      "completed": true,
      "event_log_sha256": "82cebe16528fa5e22c107cc68bbbdeebaa273ae03742fdf69f58f96563397c38",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185511",
      "total_cost_usd": 0.04121224
    },
    {
      "completed": true,
      "event_log_sha256": "6cd4056140efe84230d9497dad41f26f811ccbbe56e4c86494ee09f9b81a58ac",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185559",
      "total_cost_usd": 0.03943924
    },
    {
      "completed": true,
      "event_log_sha256": "f01a5ebca409ad9b15d4b1d16e8a554d65fbe69178ea54e85fd2b87dbfa7f328",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185097",
      "total_cost_usd": 0.4318035
    },
    {
      "completed": true,
      "event_log_sha256": "e0d1fd3ce728f8f372d40b01f48061132248ec1e912a8eb42cde55de9e0301e2",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185106",
      "total_cost_usd": 0.46089749999999996
    },
    {
      "completed": true,
      "event_log_sha256": "427df5c34fa340f8b62b59b41145a7e3abcda936d585793b34fc36f5cc3aec56",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185115",
      "total_cost_usd": 0.357217
    },
    {
      "completed": true,
      "event_log_sha256": "97bc375e9568a3faee1cdd5267baf3b92f6a5bdb5e1705427f5d1312f5550865",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185286",
      "total_cost_usd": 0.36915925
    },
    {
      "completed": true,
      "event_log_sha256": "bdc21369370377e22e83c4a13653f3c735b3a63a525a55a45a6dc4259faebf0b",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185294",
      "total_cost_usd": 0.47649125000000003
    },
    {
      "completed": true,
      "event_log_sha256": "7d4b6edc06cc90a46109903754027fcef0397b3e1249da5d451d17bb0cd6a5e4",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185303",
      "total_cost_usd": 0.5532027500000001
    },
    {
      "completed": true,
      "event_log_sha256": "0d2b3b682381a4a6b2a94e92c333c3b7d876cf043ba5673e5e081578d3811a91",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185471",
      "total_cost_usd": 0.46007
    },
    {
      "completed": true,
      "event_log_sha256": "73e2f10d201caaec9842d67f6a73a2196009ef0927c3fe8030d4324ac2cb4397",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185480",
      "total_cost_usd": 0.42960775
    },
    {
      "completed": true,
      "event_log_sha256": "d0e85c139774a0a4c1a52f19ce648093597dcba97dc2c71c9921ed7c0344e534",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185510",
      "total_cost_usd": 0.369694
    },
    {
      "completed": true,
      "event_log_sha256": "62bbe6158e42a054fbaff298e7a646c2fa2e493135bffc29ceabfb8ed6b0676e",
      "included": true,
      "resolved_config_sha256": "5efdd8c1e9835743d76496869695471284ad8c4281d5e7a958a08daeb614ec86",
      "role": "treatment:covenant:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185539",
      "total_cost_usd": 0.5403852499999999
    },
    {
      "completed": true,
      "event_log_sha256": "284cb040e31162d538c80b03829be57fc34765bf63ba3c191bf8095968581eb8",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185092",
      "total_cost_usd": 0.03311488
    },
    {
      "completed": true,
      "event_log_sha256": "4cd39f044a0f1ae6b26d7a21e267a909a3f2b981d19284532147feb469fac626",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185102",
      "total_cost_usd": 0.02969846
    },
    {
      "completed": true,
      "event_log_sha256": "3b98aa6df2f27ab60369f7c4412a120ac23f45c0d0ca91e694cec4f7a9a58d7f",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185112",
      "total_cost_usd": 0.02699074
    },
    {
      "completed": true,
      "event_log_sha256": "dda6e17aa826aefbbeea6ff6f23b2d4af10825301c661e53f19df904486868b2",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185284",
      "total_cost_usd": 0.023681840000000003
    },
    {
      "completed": true,
      "event_log_sha256": "b895f2237d973a05e08f6acd8b25c323cc4c5fbb70ad8590d0190afd0af05545",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185291",
      "total_cost_usd": 0.022169759999999997
    },
    {
      "completed": true,
      "event_log_sha256": "238cc77e99f4d553aca6c656bca96e6c2da5f5cd092b9f9bf878215edb1759d0",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185300",
      "total_cost_usd": 0.03225848
    },
    {
      "completed": true,
      "event_log_sha256": "131702a64b495058634f93f91e97d714f152bd9cdc70c724559d4915f91d3775",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185369",
      "total_cost_usd": 0.02303114
    },
    {
      "completed": true,
      "event_log_sha256": "da046ba1aa77e6f72a5d783e5f71ca1e5b84900d981eacbfa68d5500845ee5da",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185497",
      "total_cost_usd": 0.03857162
    },
    {
      "completed": true,
      "event_log_sha256": "d35d70c9741e9e7fd927f04686ed968964017ca12489373fa0836fad834fc2b4",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185508",
      "total_cost_usd": 0.0349981
    },
    {
      "completed": true,
      "event_log_sha256": "8de45bef893490b2a9543822f922802088cdc2bd5d323d31cc4670d82e409bc7",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-luna",
      "run_dir": "runs/repo_stewardship/1787185536",
      "total_cost_usd": 0.03783796
    },
    {
      "completed": true,
      "event_log_sha256": "a2647cf3d0caf60097c2f8d4a4d449e1607b5ec4fd160c2bd39f6eac1983a67c",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185091",
      "total_cost_usd": 0.42238275000000003
    },
    {
      "completed": true,
      "event_log_sha256": "d1ef78ed906cfec0e08bb97df85815c4b8fb0e5a201b5b1d512da06213831622",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185101",
      "total_cost_usd": 0.34099075
    },
    {
      "completed": true,
      "event_log_sha256": "a606722395a0845a23f1f2ec9c8de2611cc1fe9fe01cff299fadd2fd58ae986d",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185113",
      "total_cost_usd": 0.4545585
    },
    {
      "completed": true,
      "event_log_sha256": "b366665dc3253c32982c39ec4257282544e8adcba9be8348794d63aecc7923da",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185283",
      "total_cost_usd": 0.41145075
    },
    {
      "completed": true,
      "event_log_sha256": "a69db8654983b560e93b8b14466221df81d9eb29bef58e4d7bc1bb94d1a84fc0",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185290",
      "total_cost_usd": 0.37564200000000003
    },
    {
      "completed": true,
      "event_log_sha256": "384a20a0da742f007fc58c4eae7cdf5a964b3cc074459ef598858470aef8e901",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185299",
      "total_cost_usd": 0.55965225
    },
    {
      "completed": true,
      "event_log_sha256": "a3124badd173b4fa4a9a7fbe1a33f6818fbfb2280f401fa57e4d5c2c332e6b6b",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185328",
      "total_cost_usd": 0.425361
    },
    {
      "completed": true,
      "event_log_sha256": "24c5891f9c8b055e47cc064b7d90434ff11af1318525a2e2b9da5952b6df8906",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185477",
      "total_cost_usd": 0.41683349999999997
    },
    {
      "completed": true,
      "event_log_sha256": "dd9a8400f60c8f7756b5a92a7ba31ddcf7a4975c202371974057c41f31ef62af",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185507",
      "total_cost_usd": 0.43672975
    },
    {
      "completed": true,
      "event_log_sha256": "c74431e11f4facc8ae4f0900979ba87d09bcf3172236c9f17c598987d183b36a",
      "included": true,
      "resolved_config_sha256": "24dd49cf618d56f25645b1f601e4f9b83138369ce3055965b4f7952859f03df2",
      "role": "treatment:rule:gpt-5.6-terra",
      "run_dir": "runs/repo_stewardship/1787185537",
      "total_cost_usd": 0.40416225
    }
  ],
  "schema_version": 2,
  "study_id": "STUDY-015",
  "worktree_dirty": true
}
-->

## Question

Two questions that the five-family comparison cannot answer, because every
cross-model contrast so far confounds **capability** with **provider stack**.

1. **Does capability alone reproduce the pattern?** `gpt-5.6-luna`,
   `gpt-5.6-terra`, and `gpt-5.6-sol` run on one API, one reasoning-effort
   setting, one caching regime. Only the capability tier varies. Every previous
   comparison — Opus with prompt caching at default effort, GPT on the Responses
   API at high effort, Kimi on chat-completions through OpenRouter — varied both
   at once, and both EXP-050 and EXP-051 record that as an unresolved limitation.

2. **Where is a covenant increment measurable at all?** The evidence assembled
   across five families says the increment can only exist where the imposed rule
   is *insufficient*, because two constants cannot differ:

   | model | where `rule` lands | headroom | `rule` vs `covenant` |
   |---|---|---|---|
   | `claude-opus-5`, `kimi-k3`, `gpt-5.6-sol` | 0.00 | none | unmeasurable (zero variance) |
   | `claude-sonnet-5` | 0.13 | little | separated, p = 0.0021, favouring `rule` |
   | `claude-haiku-4-5` | 0.93 | large | +0.134, p = 0.082, favouring `covenant` |

   Weaker models should leave more headroom. This experiment puts that on a
   controlled ladder instead of inferring it across four vendors.

## Expected decision

Two gates, both read on the **`baseline` and `rule` arms**; the `covenant` arm is
carried for completeness but decides nothing at this n.

**Gate A — monotone capability effect.** `critical_defects_remaining` in the
`baseline` arm should be ordered `luna` ≥ `terra` ≥ `sol` (weaker leaves more
defects). `sol` is already measured at 1.10.

- **Ordered as predicted** → the cross-family pattern is reproduced by capability
  alone, inside one stack. The Opus result is then most parsimoniously read as a
  capability/behaviour property rather than a provider-stack artefact, and the
  headline claim across the program strengthens.
- **Not ordered** → capability alone does not produce the pattern, and every
  cross-model claim in EXP-048, EXP-050, and EXP-051 must be restated as being
  about configured stacks rather than about model capability.

**Gate B — headroom.** The `rule` arm's `critical_defects_remaining` must be
strictly greater than 0.00 with non-zero variance on at least one of the two
models.

- **Passes** → that model is where the rule is insufficient, and therefore the
  only place in this stack where a covenant increment could be detected. It
  becomes the target for a properly powered rule-versus-covenant batch, which is
  the cheapest available test of the program's central claim.
- **Fails on both** → the rule saturates at every capability tier of this family,
  the headroom hypothesis is not supported within a stack, and Haiku remains the
  only candidate cell in the entire program.

**Preregistered prediction.** `luna` shows the most headroom, `terra` intermediate,
`sol` none — monotone in price and presumed capability. Recorded so a non-monotone
result cannot be narrated afterwards as expected.

**Explicitly not a gate.** `rule` versus `covenant` at n=10 has a minimum
detectable difference of roughly 0.75 — larger than the entire governance effect.
No covenant conclusion will be drawn from this experiment in either direction.
This is a targeting experiment whose output is *where to spend the next runs*.

**Stopping rule.** Ten simulations per arm per model, sixty total, launched
interleaved across arms within each model. No interim look, no extension. A run
that does not emit `simulation_ended` is excluded and replaced by one relaunch;
more than five such failures across the experiment aborts it.

**Zero-activity runs.** Same `idle_stall` criterion as EXP-051 through EXP-053.

## Design

**Instrument:** `repo_stewardship`, discoverable disclosure mode, judge oracle,
live reviewer. Unmodified. Configs hash-identical to every experiment since
EXP-048.

**Models:** `gpt-5.6-terra` and `gpt-5.6-luna`, both via `openai`, both at
`openai_reasoning_effort="high"` with `max_tokens=32768` — byte-identical model
settings to the `gpt-5.6-sol` runs in EXP-050, which supplies the third rung
without being re-run. Judge `claude-haiku-4-5-20251001` via `anthropic`. Seed 42.

**Price as a capability proxy.** $0.20/$1.20, $2.50/$15.00, and $5.00/$30.00 per
Mtok for luna, terra, and sol. Price is a vendor's ordering, not a measured
capability ranking, and Gate A is stated as a prediction about that ordering
precisely so it can fail.

**Platform change.** `gpt-5.6-luna` was absent from the pricing table, so
`find_pricing` returned `None` and every run would have recorded $0.00. Added
before launch, following the same trap recorded in EXP-051.

**Replication unit:** one simulation. Ten per arm per model.

**Budget.** Terra at roughly half sol's rate projects to about $0.40 per run;
luna at a twenty-fifth projects to about $0.04. Sixty runs projects to
roughly $13. Abandoned rather than extended above $40.

## Outcomes inspected

Scored by EXP-048's
[`frontier_ceiling.py`](../EXP-048-frontier-ceiling-repo-stewardship/analysis/frontier_ceiling.py),
unmodified, so both rungs are commensurable with `gpt-5.6-sol` and with all four
other families.

**Gate A.** `critical_defects_remaining`, `baseline` arm, per model, with range.

**Gate B.** `critical_defects_remaining`, `rule` arm, per model, with range and
variance.

**Descriptive.** The remaining twelve outcomes, plus the discovery decomposition
from
[`why_opus_differs.py`](../EXP-051-kimi-k3-frontier-ceiling/analysis/why_opus_differs.py),
which is the direct test of whether the sequencing mechanism — repair before
shipping — tracks capability within one stack.

**Instrument check.** `critical_defects_remaining == 2 − repairs`.

**Analysis rule fixed in advance.** Only Gates A and B decide anything.

## Provenance

- Base commit: `0c2f6a7255a34783b5007d99539f022ec179cb72`
- Worktree dirty at planning: `true`. Provisional; artifact-verifiable.
- Model/provider: `openai:gpt-5.6-terra`, `openai:gpt-5.6-luna`; seed 42; 7 rounds.
- Source/fork boundary: none. Sixty fresh runs.
- Third rung: EXP-050's `gpt-5.6-sol` runs, not re-run here, listed with hashes in
  that record.

## Result

**Gate A — partially supported. Gate B — passes, on `luna` and only on `luna`.**

### Gate A: capability ordering in the ungoverned baseline

| model | price in/out per Mtok | criticals left | variance |
|---|---|---|---|
| `gpt-5.6-luna` | $0.20 / $1.20 | **2.00** (2–2) | 0.000 |
| `gpt-5.6-terra` | $2.50 / $15.00 | **1.00** (0–2) | 0.200 |
| `gpt-5.6-sol` | $5.00 / $30.00 | **1.10** (0–2) | 0.690 |

Predicted `luna` ≥ `terra` ≥ `sol`. Observed `luna` ≫ `terra` ≈ `sol`, with sol
0.10 *worse* than terra — inside noise, but not the predicted strict ordering.

The honest reading: **the ordering holds at the bottom of the ladder and flattens
at the top.** The cheapest tier fails invariantly — `luna`'s baseline leaves
exactly 2.00 criticals in all ten runs, repairs exactly 0.00 in all ten, and ships
a change carrying a known defect in every single run. The two upper tiers are
indistinguishable from each other.

This is enough to say capability alone reproduces the qualitative pattern inside
one stack — a weaker model fails more — without licensing a monotone
capability→compliance curve. Two of the three rungs are tied.

### Gate B: headroom above the rule floor

| model | `rule` arm | variance | headroom |
|---|---|---|---|
| `gpt-5.6-luna` | **0.50** (0–2) | 0.650 | **yes** |
| `gpt-5.6-terra` | 0.00 (0–0) | 0.000 | no |
| `gpt-5.6-sol` | 0.00 (0–0) | 0.000 | no |

`luna` is the only rung in this stack where the imposed rule is insufficient. On
`terra` and `sol` the rule drives compliance to a constant zero, exactly as on
`claude-opus-5` and `kimi-k3`, and two constants cannot differ.

**The headroom hypothesis survives its first controlled test.** It was inferred
across four vendors; here it reproduces inside one stack, one API, one
reasoning-effort setting, with only the capability tier varying.

### The descriptive contrast, reported as preregistered

`rule` versus `covenant` was explicitly declared **not a gate** in this record, on
the stated grounds that n=10 gives a minimum detectable difference near 0.75. That
declaration stands and no covenant conclusion is drawn here. The values:

| model | rule | covenant | difference | p |
|---|---|---|---|---|
| `gpt-5.6-luna` | 0.50 | 1.50 | **−1.00** | **0.0236** |
| `gpt-5.6-terra` | 0.00 | 0.00 | 0.00 | 1.0000 |
| `gpt-5.6-sol` | 0.00 | 0.40 | −0.40 | 0.4677 |

Two facts must be recorded without being converted into a conclusion:

1. The `luna` difference of 1.00 **exceeds the minimum detectable difference this
   record declared in advance**, so it is not a case of reading noise below the
   resolution of the design.
2. It points the same direction as
   [EXP-052](../EXP-052-sonnet-rule-arm/experiment.md)'s `claude-sonnet-5` result
   (−0.73, p = 0.0021): the **imposed rule outperforms the affirmed covenant**.

Unlike EXP-052, this cell has **no non-concurrency confound** — all three arms
were launched interleaved in one batch, round-robin across arms, which is the
control EXP-052 lacked. That makes `luna` the first arm-controlled cell in the
program pointing this way.

It remains one cell at n=10 whose contrast was preregistered as non-decisive. It
is a hypothesis for a powered test, not a result.

**Cost.** $13.71 for sixty runs. `luna` ran at $0.03 per simulation.

## Outcome

`mixed` — Gate A partially supported (ordering at the bottom, flat at the top),
Gate B supported on one of two models.

The experiment did what it was built to do: it identified **where to spend the
next runs.** `gpt-5.6-luna` is the cheapest cell in the entire program where the
covenant question is measurable at all, at three cents per simulation.

## Validity limitations

- **Price is not capability, and the ordering only partly held.** Gate A was
  stated against the vendor's price tiers. `terra` and `sol` came out tied, so
  either the tiers do not track capability on this task or the task does not
  discriminate between them. No independent capability benchmark was applied.
- **The third rung is not concurrent.** `gpt-5.6-sol` was run earlier the same day
  in EXP-050; `terra` and `luna` ran now. The luna-versus-terra comparison is
  concurrent and clean; every comparison involving `sol` carries the same
  non-concurrency defect EXP-053 exists to fix.
- **`luna`'s baseline is itself a floor.** 2.00 of 2 criticals with zero variance
  means the baseline cannot get worse, so baseline-versus-governed effect sizes on
  this model are bounded by the instrument rather than measured.
- **Ten runs per arm.** Adequate for Gates A and B, which ask about ordering and
  about whether a quantity is non-zero. The rule-versus-covenant contrast was
  preregistered as non-decisive and is reported as such despite reaching p < 0.05.
- **One vendor family.** Removing the stack confound within OpenAI's tiers does not
  establish that the `claude-opus-5` result is capability rather than stack. It
  removes one competing explanation.
- **Not a covenant result.** Nothing here licenses the word `covenant` as a
  supported claim in either direction.

## What it changed

1. **Supplies the first controlled test of the headroom hypothesis.** Inferred
   across four vendors, reproduced inside one stack. Where the rule saturates, the
   covenant question is unmeasurable; `luna` is where it is not.
2. **Identifies the cheapest measurable cell in the program.** `gpt-5.6-luna` at
   $0.03 per run, with the rule sitting at 0.50 and real variance. A 60-per-arm
   powered rule-versus-covenant batch there costs under $10 — against the $532 the
   program has already spent without ever being able to test the claim.
3. **Produces a second, arm-controlled cell pointing rule-over-covenant.** EXP-052
   found this on Sonnet with a non-concurrent confound. This cell has no such
   confound. Two independent models now point the same way, which moves the
   question from "probable artefact" to "worth powering."
4. **Weakens the pure-capability reading of the Opus ceiling.** `terra` and `sol`
   tie despite a 2× price gap, so compliance is not a smooth function of tier
   within this family.

## Traps found

- **A contrast preregistered as non-decisive can still come back significant.**
  `luna`'s rule-versus-covenant reached p = 0.0236 and exceeded the record's own
  stated minimum detectable difference. The preregistration is what makes it
  reportable-but-not-concludable; without it, this would have been written up as a
  finding on the strength of a single n=10 cell.
- **A missing pricing entry silently zeroes an entire experiment's cost.**
  `gpt-5.6-luna` was absent from the table, so `find_pricing` returned `None` and
  all thirty runs would have recorded $0.00 — the same trap logged in EXP-051, hit
  a second time within hours because the fix was per-model rather than structural.
  A model absent from the pricing table should fail loudly at launch, not record a
  false zero.
- **Brace expansion in a recorded command is not a command.** The validator
  rejected `configs/{baseline,rule,covenant}-resolved.json`. A record whose
  commands cannot be executed verbatim is worse than one with six explicit lines.
