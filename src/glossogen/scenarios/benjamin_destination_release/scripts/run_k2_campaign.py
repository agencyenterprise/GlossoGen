"""Launch a frozen destination-release K2 campaign with live publication."""

import argparse
import asyncio
import re
import sys
from pathlib import Path
from typing import Self

from pydantic import BaseModel, model_validator

from glossogen.scenarios.benjamin_destination_release.scripts.run_k1_campaign import (
    SCENARIO_NAME,
    run_campaign_stage,
)
from glossogen.scenarios.benjamin_release_pipeline.scripts.run_campaign import (
    CampaignConfig,
    StagePlan,
    jobs_for_stage,
)


class K2CampaignManifest(BaseModel):
    """Immutable ungoverned observation matrix for the K2 gate."""

    experiment_id: str
    scenario: str
    seeds: list[int]
    models: list[str]
    configs: list[CampaignConfig]
    stages: dict[str, StagePlan]

    @model_validator(mode="after")
    def validate_matrix(self) -> Self:
        """Require one complete two-cell K2 matrix over three fresh seeds."""
        if re.fullmatch(r"EXP-\d{3}", self.experiment_id) is None:
            raise ValueError("campaign manifest must identify one EXP-NNN record")
        if self.scenario != SCENARIO_NAME:
            raise ValueError(f"campaign scenario must be {SCENARIO_NAME}")
        if len(self.seeds) != 3 or len(set(self.seeds)) != 3:
            raise ValueError("campaign must preregister exactly three distinct seeds")
        if set(self.stages) != {"k2"}:
            raise ValueError("K2 manifest must contain only the k2 stage")
        config_keys = {(config.stage, config.cell_id, config.seed) for config in self.configs}
        if len(config_keys) != len(self.configs):
            raise ValueError("campaign config assignments must be unique")
        stage = self.stages["k2"]
        if not stage.seed_schedule:
            raise ValueError("K2 must freeze an explicit interleaved seed schedule")
        if set(stage.seed_schedule) != set(self.seeds):
            raise ValueError("K2 seed schedule must use every preregistered seed")
        for cell_id in stage.cell_order:
            for seed in self.seeds:
                if ("k2", cell_id, seed) not in config_keys:
                    raise ValueError(f"missing K2 config for cell={cell_id}, seed={seed}")
        return self


def _parse_args() -> argparse.Namespace:
    """Parse one K2 campaign invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--provider", type=str, required=True)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--max-concurrency", type=int, required=True)
    parser.add_argument("--max-agent-turns", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_k2_manifest(path: Path) -> K2CampaignManifest:
    """Read and validate the immutable K2 manifest."""
    return K2CampaignManifest.model_validate_json(path.read_text(encoding="utf-8"))


async def _async_main(args: argparse.Namespace) -> int:
    """Validate and launch all K2 jobs for one family."""
    repo_root = Path(__file__).resolve().parents[5]
    manifest = load_k2_manifest(path=args.manifest.resolve())
    if args.model not in manifest.models:
        raise ValueError(f"model is not preregistered in manifest: {args.model}")
    jobs = jobs_for_stage(manifest=manifest, stage_name="k2", repo_root=repo_root)
    results = await run_campaign_stage(
        jobs=jobs,
        runs_dir=args.runs_dir.resolve(),
        model=args.model,
        provider=args.provider,
        max_agent_turns=args.max_agent_turns,
        max_concurrency=args.max_concurrency,
        dry_run=args.dry_run,
        experiment_id=manifest.experiment_id,
    )
    failures = [result for result in results if result.return_code != 0]
    print(
        f"stage=k2 planned={len(jobs)} completed={len(results)} "
        f"failures={len(failures)} dry_run={args.dry_run}",
        flush=True,
    )
    if failures:
        return 1
    if len(results) != len(jobs):
        return 2
    return 0


def main() -> int:
    """Run the K2 campaign."""
    return asyncio.run(_async_main(args=_parse_args()))


if __name__ == "__main__":
    sys.exit(main())
