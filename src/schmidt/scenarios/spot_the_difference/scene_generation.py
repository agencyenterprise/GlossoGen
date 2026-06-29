"""Procedural per-round scene generation for the spot_the_difference scenario.

Each round the environment builds one scene as a set of objects — each a
``shape, color, size`` bundle placed on a distinct ``(column, row)`` cell of a
``grid_size`` x ``grid_size`` grid — then a near-identical copy (scene B) with
exactly K planted differences drawn from a fixed taxonomy: an attribute
changed, an object moved, an object added, or an object removed. The left
viewer sees scene A and the right viewer sees scene B; neither sees the other
scene nor the planted differences, so a difference is only discoverable by
exchanging descriptions.

Each round is built from an independent per-round RNG seeded from
``(seed, round_number)``, so a round's content depends only on the seed and
that round's own configuration (toggling one warmup round does not shift the
others). Every edit targets a distinct object and reserves distinct cells, so
the two scenes differ in exactly K detectable, isolated ways.
"""

import logging
import random
from typing import NamedTuple

from schmidt.scenarios.spot_the_difference.ids import DifferenceKind

logger = logging.getLogger(__name__)

SHAPES = ["circle", "square", "triangle", "star", "diamond", "hexagon", "heart", "cross"]
COLORS = ["red", "blue", "green", "yellow", "purple", "orange", "pink", "brown"]
SIZES = ["small", "medium", "large"]

_ATTRIBUTE_NAMES = ["shape", "color", "size"]
_VALUES_BY_ATTRIBUTE: dict[str, list[str]] = {"shape": SHAPES, "color": COLORS, "size": SIZES}

_MAX_DRAW_ATTEMPTS = 10000


class SceneObject(NamedTuple):
    """One object in a scene: a shape/color/size bundle at a grid cell."""

    shape: str
    color: str
    size: str
    column: int
    row: int

    @property
    def bundle(self) -> tuple[str, str, str]:
        """The attribute triple identifying this object independent of position."""
        return (self.shape, self.color, self.size)


class PlantedDifference(NamedTuple):
    """One ground-truth difference between scene A and scene B.

    ``scene_a_object`` / ``scene_b_object`` are the object as it appears in
    each scene; one is ``None`` for added (absent from A) or removed (absent
    from B) objects. ``attribute_name`` names the changed dimension for
    ``attribute_changed`` and is ``None`` otherwise. ``description`` is the
    canonical human-readable phrasing the LLM judge matches submissions
    against.
    """

    kind: DifferenceKind
    description: str
    scene_a_object: SceneObject | None
    scene_b_object: SceneObject | None
    attribute_name: str | None


class DiffCase(NamedTuple):
    """A single spot_the_difference case presented per round."""

    case_number: int
    grid_size: int
    difference_count: int
    scene_a: tuple[SceneObject, ...]
    scene_b: tuple[SceneObject, ...]
    differences: tuple[PlantedDifference, ...]


def render_object(obj: SceneObject) -> str:
    """Render one object as ``<size> <color> <shape> at column C, row R``."""
    return f"{obj.size} {obj.color} {obj.shape} at column {obj.column}, row {obj.row}"


def _describe_bundle(obj: SceneObject) -> str:
    """Render one object's attributes without position."""
    return f"{obj.size} {obj.color} {obj.shape}"


def get_cases(
    seed: int,
    round_count: int,
    grid_size: int,
    object_count_values: list[int],
    object_count_weights: list[int],
    difference_count_values: list[int],
    difference_count_weights: list[int],
    difference_kinds: list[str],
    easy_round_numbers: frozenset[int],
) -> list[DiffCase]:
    """Generate per-round difference cases deterministically from ``seed``."""
    kinds = [DifferenceKind(value) for value in difference_kinds]
    cases: list[DiffCase] = []
    for case_index in range(round_count):
        case_number = case_index + 1
        round_rng = random.Random(f"{seed}-{case_number}")
        object_count = round_rng.choices(object_count_values, weights=object_count_weights, k=1)[0]
        if case_number in easy_round_numbers:
            difference_count = 1
        else:
            difference_count = round_rng.choices(
                difference_count_values, weights=difference_count_weights, k=1
            )[0]
        cases.append(
            _build_one_case(
                rng=round_rng,
                case_number=case_number,
                grid_size=grid_size,
                object_count=object_count,
                difference_count=difference_count,
                kinds=kinds,
            )
        )
    return cases


def _build_one_case(
    rng: random.Random,
    case_number: int,
    grid_size: int,
    object_count: int,
    difference_count: int,
    kinds: list[DifferenceKind],
) -> DiffCase:
    """Build scene A, plant ``difference_count`` isolated edits to form scene B."""
    all_cells = [
        (column, row) for column in range(1, grid_size + 1) for row in range(1, grid_size + 1)
    ]
    chosen_cells = rng.sample(all_cells, k=object_count)
    bundles = _draw_distinct_bundles(rng=rng, count=object_count)
    scene_a: list[SceneObject] = [
        SceneObject(shape=shape, color=color, size=size, column=column, row=row)
        for (column, row), (shape, color, size) in zip(chosen_cells, bundles)
    ]
    builder = _SceneBBuilder(scene_a=scene_a, all_cells=all_cells)
    drawn_kinds = [rng.choice(kinds) for _ in range(difference_count)]
    differences: list[PlantedDifference] = []
    for kind in drawn_kinds:
        difference = builder.apply_edit(rng=rng, kind=kind)
        differences.append(difference)
    return DiffCase(
        case_number=case_number,
        grid_size=grid_size,
        difference_count=difference_count,
        scene_a=tuple(scene_a),
        scene_b=tuple(builder.finalize()),
        differences=tuple(differences),
    )


def _draw_distinct_bundles(rng: random.Random, count: int) -> list[tuple[str, str, str]]:
    """Draw ``count`` distinct ``(shape, color, size)`` bundles."""
    seen: set[tuple[str, str, str]] = set()
    out: list[tuple[str, str, str]] = []
    attempts = 0
    while len(out) < count and attempts < _MAX_DRAW_ATTEMPTS:
        attempts += 1
        bundle = (rng.choice(SHAPES), rng.choice(COLORS), rng.choice(SIZES))
        if bundle in seen:
            continue
        seen.add(bundle)
        out.append(bundle)
    return out


class _SceneBBuilder:
    """Mutates a copy of scene A into scene B by applying isolated edits.

    Each edit consumes a distinct object index (attribute change, move,
    remove) or only a fresh cell (add), reserving cells and bundles so no two
    edits interact and the scenes end up differing in exactly one detectable
    way per edit.
    """

    def __init__(self, scene_a: list[SceneObject], all_cells: list[tuple[int, int]]) -> None:
        self._scene_a = scene_a
        self._all_cells = all_cells
        self._b_objects: list[SceneObject | None] = list(scene_a)
        self._added: list[SceneObject] = []
        self._locked_indices: set[int] = set()
        self._occupied_cells: set[tuple[int, int]] = {(obj.column, obj.row) for obj in scene_a}
        self._used_bundles: set[tuple[str, str, str]] = {obj.bundle for obj in scene_a}

    def finalize(self) -> list[SceneObject]:
        """Return scene B as the surviving original objects plus added objects."""
        survivors = [obj for obj in self._b_objects if obj is not None]
        return survivors + self._added

    def apply_edit(self, rng: random.Random, kind: DifferenceKind) -> PlantedDifference:
        """Apply one edit of ``kind`` and return its ground-truth difference."""
        if kind == DifferenceKind.ATTRIBUTE_CHANGED:
            return self._apply_attribute_change(rng=rng)
        if kind == DifferenceKind.OBJECT_MOVED:
            return self._apply_move(rng=rng)
        if kind == DifferenceKind.OBJECT_ADDED:
            return self._apply_add(rng=rng)
        return self._apply_remove(rng=rng)

    def _pick_unlocked_index(self, rng: random.Random) -> int:
        """Return a random object index not yet consumed by another edit."""
        available = [i for i in range(len(self._scene_a)) if i not in self._locked_indices]
        index = rng.choice(available)
        self._locked_indices.add(index)
        return index

    def _pick_empty_cell(self, rng: random.Random) -> tuple[int, int]:
        """Return a random cell empty in both scenes and reserve it."""
        empty = [cell for cell in self._all_cells if cell not in self._occupied_cells]
        cell = rng.choice(empty)
        self._occupied_cells.add(cell)
        return cell

    def _apply_attribute_change(self, rng: random.Random) -> PlantedDifference:
        """Change one attribute of a fresh object, keeping its bundle unique."""
        index = self._pick_unlocked_index(rng=rng)
        original = self._scene_a[index]
        for _ in range(_MAX_DRAW_ATTEMPTS):
            attribute_name = rng.choice(_ATTRIBUTE_NAMES)
            new_value = rng.choice(_VALUES_BY_ATTRIBUTE[attribute_name])
            if new_value == getattr(original, attribute_name):
                continue
            changed = original._replace(**{attribute_name: new_value})
            if changed.bundle in self._used_bundles:
                continue
            self._used_bundles.add(changed.bundle)
            self._b_objects[index] = changed
            return PlantedDifference(
                kind=DifferenceKind.ATTRIBUTE_CHANGED,
                description=(
                    f"Attribute change at column {original.column}, row {original.row}: "
                    f"a {_describe_bundle(obj=original)} in scene A versus a "
                    f"{_describe_bundle(obj=changed)} in scene B "
                    f"(same position; {attribute_name} differs)."
                ),
                scene_a_object=original,
                scene_b_object=changed,
                attribute_name=attribute_name,
            )
        raise RuntimeError("Could not find a distinct attribute change")

    def _apply_move(self, rng: random.Random) -> PlantedDifference:
        """Relocate a fresh object to a cell empty in both scenes."""
        index = self._pick_unlocked_index(rng=rng)
        original = self._scene_a[index]
        column, row = self._pick_empty_cell(rng=rng)
        moved = original._replace(column=column, row=row)
        self._b_objects[index] = moved
        return PlantedDifference(
            kind=DifferenceKind.OBJECT_MOVED,
            description=(
                f"Position change: a {_describe_bundle(obj=original)} is at column "
                f"{original.column}, row {original.row} in scene A but at column "
                f"{moved.column}, row {moved.row} in scene B."
            ),
            scene_a_object=original,
            scene_b_object=moved,
            attribute_name=None,
        )

    def _apply_add(self, rng: random.Random) -> PlantedDifference:
        """Add a new object to scene B at a fresh cell with a unique bundle."""
        column, row = self._pick_empty_cell(rng=rng)
        for _ in range(_MAX_DRAW_ATTEMPTS):
            bundle = (rng.choice(SHAPES), rng.choice(COLORS), rng.choice(SIZES))
            if bundle in self._used_bundles:
                continue
            self._used_bundles.add(bundle)
            shape, color, size = bundle
            added = SceneObject(shape=shape, color=color, size=size, column=column, row=row)
            self._added.append(added)
            return PlantedDifference(
                kind=DifferenceKind.OBJECT_ADDED,
                description=(
                    f"Extra object in scene B: a {render_object(obj=added)} that is absent "
                    f"from scene A."
                ),
                scene_a_object=None,
                scene_b_object=added,
                attribute_name=None,
            )
        raise RuntimeError("Could not find a distinct bundle for an added object")

    def _apply_remove(self, rng: random.Random) -> PlantedDifference:
        """Remove a fresh object from scene B (present in A, absent from B)."""
        index = self._pick_unlocked_index(rng=rng)
        original = self._scene_a[index]
        self._b_objects[index] = None
        return PlantedDifference(
            kind=DifferenceKind.OBJECT_REMOVED,
            description=(
                f"Missing object in scene B: a {render_object(obj=original)} present in "
                f"scene A but absent from scene B."
            ),
            scene_a_object=original,
            scene_b_object=None,
            attribute_name=None,
        )
