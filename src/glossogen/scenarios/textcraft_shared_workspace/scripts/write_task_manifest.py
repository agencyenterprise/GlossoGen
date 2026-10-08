"""Write a certified task manifest for the ``task_manifest`` knob.

One task per seed, ``--first-seed`` onward, all with the same grid and raw
materials. The file is a JSON list of tasks, which every arm of an experiment
can replay so they all play the same instances::

    python -m glossogen.scenarios.textcraft_shared_workspace.scripts.write_task_manifest \\
        --output tasks.json --first-seed 1000 --count 16 --width 4 --span 2 \\
        --quantity-scale 2 --resource-slack-fraction 0.2 --max-fan-in 2 \\
        --cross-edge-density 0.3 --max-raw-inputs 2
"""

import argparse
import json
from pathlib import Path

from glossogen.scenarios.textcraft_shared_workspace.tasks import generate_task


def main() -> None:
    """Parse the grid, generate and certify each task, and write the list."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-seed", type=int, required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--span", type=int, required=True)
    parser.add_argument("--quantity-scale", type=int, required=True)
    parser.add_argument("--resource-slack-fraction", type=float, required=True)
    parser.add_argument("--max-fan-in", type=int, required=True)
    parser.add_argument("--cross-edge-density", type=float, required=True)
    parser.add_argument(
        "--raw-material-count",
        type=int,
        help="distinct raw items, 1 to 3; drawn per task when omitted",
    )
    parser.add_argument("--max-raw-inputs", type=int, required=True)
    args = parser.parse_args()
    tasks = [
        generate_task(
            seed=args.first_seed + index,
            width=args.width,
            span=args.span,
            quantity_scale=args.quantity_scale,
            resource_slack_fraction=args.resource_slack_fraction,
            max_fan_in=args.max_fan_in,
            cross_edge_density=args.cross_edge_density,
            raw_material_count=args.raw_material_count,
            max_raw_inputs=args.max_raw_inputs,
        ).model_dump()
        for index in range(args.count)
    ]
    args.output.write_text(json.dumps(tasks, indent=2) + "\n")


if __name__ == "__main__":
    main()
