"""Synthetic layered crafting tasks with executable witnesses.

Recipes use TextCraft's craft syntax but are synthetic: item names are opaque
IDs, so no Minecraft data or memorized recipe knowledge helps. A task is a grid
of recipes. Each column ends in one target, and every recipe after the first
layer consumes the previous layer's outputs.
"""

import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Recipe(BaseModel):
    """An atomic, positive integer multiset rewrite."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    output: str
    count: int = Field(ge=1)
    inputs: dict[str, int]

    @model_validator(mode="after")
    def validate_inputs(self) -> Self:
        """Reject invalid quantities and names before running an experiment."""
        if not self.inputs or any(n < 1 for n in self.inputs.values()):
            raise ValueError("recipe inputs must be positive and nonempty")
        if any(not name.isidentifier() for name in [self.output, *self.inputs]):
            raise ValueError("item names must be identifiers")
        return self

    @property
    def command(self) -> str:
        """Canonical TextCraft command; input order is fixed in manifests."""
        inputs = ", ".join(f"{n} {item}" for item, n in sorted(self.inputs.items()))
        return f"craft {self.count} {self.output} using {inputs}"


class TaskCard(BaseModel):
    """One column of the grid: its target and its recipes, first layer first."""

    target: str
    recipes: list[Recipe]


class WorkspaceTask(BaseModel):
    """Evaluator-side ground truth; agents see targets and recipes, never the witness."""

    schema_version: int = 1
    family: Literal["layered"]
    seed: int
    initial_depot: dict[str, int]
    cards: dict[str, TaskCard]
    witness: list[tuple[str, str]]

    @property
    def task_id(self) -> str:
        """A portable identifier independent of execution order or condition."""
        payload = json.dumps(self.model_dump(), sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()[:20]

    @property
    def recipes(self) -> list[Recipe]:
        """Every recipe of the task, column by column."""
        return [recipe for card in self.cards.values() for recipe in card.recipes]

    def certify(self) -> None:
        """Replay the witness to prove resource feasibility and retained targets.

        This is a centralized feasibility certificate, not proof that a
        particular team or observation condition will solve the instance.
        """
        if self.schema_version != 1 or not self.cards:
            raise ValueError("unsupported manifest schema or empty task")
        targets = [card.target for card in self.cards.values()]
        if len(set(targets)) != len(targets):
            raise ValueError("each target must be distinct")
        outputs = [recipe.output for recipe in self.recipes]
        if len(set(outputs)) != len(outputs):
            raise ValueError("manifests require one producing recipe per item")
        if set(outputs) & set(self.initial_depot):
            raise ValueError("initial resources must be raw, not crafted outputs")
        if any(card.target not in {r.output for r in card.recipes} for card in self.cards.values()):
            raise ValueError("each card must include the recipe for its own target")
        depot = Counter(self.initial_depot)
        if any(n < 0 for n in depot.values()):
            raise ValueError("negative initial resources")
        for column, command in self.witness:
            recipe = next((r for r in self.cards[column].recipes if r.command == command), None)
            if recipe is None or any(depot[i] < n for i, n in recipe.inputs.items()):
                raise ValueError("infeasible witness")
            depot.subtract(recipe.inputs)
            depot[recipe.output] += recipe.count
        required = Counter(targets)
        if any(depot[item] < count for item, count in required.items()):
            raise ValueError("witness does not retain every target")


def load_task_manifest(path: str) -> list[WorkspaceTask]:
    """Read a JSON list of tasks, as written by ``scripts/write_task_manifest.py``."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return [WorkspaceTask.model_validate(row) for row in rows]


def generate_task(
    seed: int,
    width: int,
    span: int,
    quantity_scale: int,
    resource_slack_fraction: float,
    max_fan_in: int,
    cross_edge_density: float,
    raw_material_count: int | None,
    max_raw_inputs: int,
) -> WorkspaceTask:
    """Generate a ``width`` x ``span`` recipe grid with exact work and span.

    Column ``c`` holds one recipe per layer, each consuming the same column's
    previous output. Cross edges only join adjacent layers, so every path visits
    one recipe per layer. Work is ``width * span``, span is ``span`` and every
    layer is exactly ``width`` recipes wide, whatever the density. Density zero
    gives ``width`` independent chains. Every column's first recipe draws from
    one shared set of ``raw_material_count`` raw items (chosen at random in 1..3
    when None).
    """
    if width < 1 or span < 1 or quantity_scale < 1:
        raise ValueError("invalid task dimensions")
    if not 0 <= resource_slack_fraction <= 1:
        raise ValueError("resource_slack_fraction must lie in [0, 1]")
    if max_fan_in < 1 or not 0 <= cross_edge_density <= 1:
        raise ValueError("fan-in must be positive and density must lie in [0, 1]")
    if max_raw_inputs < 1:
        raise ValueError("max raw inputs must be positive")
    rng = random.Random(seed)
    raw_count = raw_material_count
    if raw_count is None:
        raw_count = rng.randint(1, 3)
    if not 1 <= raw_count <= 3:
        raise ValueError("raw material count must be between one and three")

    columns = [f"crafter_{i + 1}" for i in range(width)]
    rng.shuffle(columns)
    symbols = [f"r{x:06d}" for x in rng.sample(range(1_000_000), raw_count + width * span)]
    raw_items = [symbols.pop() for _ in range(raw_count)]
    outputs = {column: [symbols.pop() for _ in range(span)] for column in columns}

    # parents[(column, layer)] lists the producing columns in the previous layer.
    parents: dict[tuple[str, int], list[str]] = {}
    for layer in range(1, span):
        for column in columns:
            chosen = [column]
            others = [other for other in columns if other != column]
            rng.shuffle(others)
            for other in others:
                if len(chosen) >= max_fan_in:
                    break
                if rng.random() < cross_edge_density:
                    chosen.append(other)
            parents[(column, layer)] = chosen

    demand: Counter[str] = Counter()
    for column in columns:
        demand[outputs[column][-1]] += 1  # retain every target
    for (_, layer), producers in parents.items():
        for producer in producers:
            demand[outputs[producer][layer - 1]] += 1

    raw_needs: dict[str, dict[str, int]] = {column: {} for column in columns}
    for index, item in enumerate(raw_items):
        raw_needs[columns[index % width]][item] = rng.randint(1, quantity_scale)
    for column in columns:
        desired = rng.randint(1, min(max_raw_inputs, raw_count))
        candidates = [item for item in raw_items if item not in raw_needs[column]]
        rng.shuffle(candidates)
        for item in candidates[: max(0, desired - len(raw_needs[column]))]:
            raw_needs[column][item] = rng.randint(1, quantity_scale)
    initial_depot: Counter[str] = Counter()
    for needs in raw_needs.values():
        initial_depot.update(needs)
    # Proportional slack keeps "slightly redundant" comparable across widths.
    for item in raw_items:
        initial_depot[item] += math.ceil(resource_slack_fraction * initial_depot[item])

    recipes_by_column: dict[str, list[Recipe]] = {column: [] for column in columns}
    witness: list[tuple[str, str]] = []
    for layer in range(span):
        for column in columns:
            inputs = dict(raw_needs[column])
            if layer > 0:
                inputs = {outputs[producer][layer - 1]: 1 for producer in parents[(column, layer)]}
            output = outputs[column][layer]
            recipe = Recipe(output=output, count=demand[output], inputs=inputs)
            recipes_by_column[column].append(recipe)
            witness.append((column, recipe.command))

    task = WorkspaceTask(
        family="layered",
        seed=seed,
        initial_depot=dict(initial_depot),
        cards={
            column: TaskCard(target=outputs[column][-1], recipes=recipes_by_column[column])
            for column in columns
        },
        witness=witness,
    )
    task.certify()
    return task
