"""Procedural per-round scene generation for the spot_the_difference scenario.

Each round the environment builds one scene as a set of objects — each a
``shape, color, size`` bundle on a distinct ``(column, row)`` cell of a
``grid_size`` x ``grid_size`` grid — then a near-identical copy (scene B) with
exactly K planted differences drawn from a fixed taxonomy: an attribute
changed, an object moved, an object added, or an object removed.

Two properties make the task require collaborative grounding rather than a
serialize-and-diff dump:

- The attribute vocabulary is small, so at the scene sizes used here objects
  with identical ``shape/color/size`` bundles recur. A bundle therefore does
  not identify an object; position is required to disambiguate.
- Agents never see exact ``(column, row)`` coordinates. Position is rendered
  only as a **coarse region** (a 3x3 grid of named areas) plus **relations to
  other objects in the same scene** (``a small red square to its left``).
  Those anchors are themselves possibly-duplicate objects in a layout that
  differs between the two scenes, so the two viewers' descriptions do not
  align one-to-one.

Each round is built from an independent per-round RNG seeded from
``(seed, round_number)``. Every edit targets a distinct object and reserves
distinct cells, so applying the K edits to scene A reproduces scene B exactly;
``object_moved`` always crosses a region so the move is relationally visible.
"""

import logging
import random
from typing import NamedTuple

from schmidt.scenarios.spot_the_difference.ids import DifferenceKind

logger = logging.getLogger(__name__)

# Small vocabulary (4 x 4 x 2 = 32 bundles) so that scenes of a dozen-plus
# objects necessarily contain duplicates.
SHAPES = ["circle", "square", "triangle", "star"]
COLORS = ["red", "blue", "green", "yellow"]
SIZES = ["small", "large"]

_ATTRIBUTE_NAMES = ["shape", "color", "size"]
_VALUES_BY_ATTRIBUTE: dict[str, list[str]] = {"shape": SHAPES, "color": COLORS, "size": SIZES}

# 3x3 coarse regions keyed by (row_band, col_band) with band 0 = top/left.
_REGION_NAMES: dict[tuple[int, int], str] = {
    (0, 0): "upper-left",
    (0, 1): "upper-center",
    (0, 2): "upper-right",
    (1, 0): "middle-left",
    (1, 1): "center",
    (1, 2): "middle-right",
    (2, 0): "lower-left",
    (2, 1): "lower-center",
    (2, 2): "lower-right",
}

_MAX_RELATIONS = 2


class SceneObject(NamedTuple):
    """One object in a scene: a shape/color/size bundle at a grid cell.

    ``column`` / ``row`` are the internal geometry; they are used for
    generation, the reconstruction check, region derivation, and debug/FE
    surfaces, but are never shown to the agents.
    """

    shape: str
    color: str
    size: str
    column: int
    row: int

    @property
    def bundle(self) -> tuple[str, str, str]:
        """The attribute triple; not unique within a scene."""
        return (self.shape, self.color, self.size)


class PlantedDifference(NamedTuple):
    """One ground-truth difference between scene A and scene B.

    ``scene_a_object`` / ``scene_b_object`` is ``None`` for an added object
    (absent from A) or a removed object (absent from B). ``attribute_name``
    names the changed dimension for ``attribute_changed`` and is ``None``
    otherwise. ``description`` is the canonical relational phrasing the LLM
    judge matches submissions against (filled in after both scenes are built).
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
    round_time_budget_seconds: int
    difference_count: int
    scene_a: tuple[SceneObject, ...]
    scene_b: tuple[SceneObject, ...]
    differences: tuple[PlantedDifference, ...]


def describe_bundle(obj: SceneObject) -> str:
    """Render one object's attributes without position."""
    return f"{obj.size} {obj.color} {obj.shape}"


def region_of(column: int, row: int, grid_size: int) -> str:
    """Return the coarse 3x3 region name for a cell (row 1 = top)."""
    row_band = min(2, (row - 1) * 3 // grid_size)
    col_band = min(2, (column - 1) * 3 // grid_size)
    return _REGION_NAMES[(row_band, col_band)]


def _direction_phrase(from_obj: SceneObject, to_obj: SceneObject) -> str:
    """Phrase the direction of ``to_obj`` relative to ``from_obj`` (row 1 = top)."""
    horizontal = _sign(to_obj.column - from_obj.column)
    vertical = _sign(to_obj.row - from_obj.row)
    table: dict[tuple[int, int], str] = {
        (1, 0): "to its right",
        (-1, 0): "to its left",
        (0, -1): "above it",
        (0, 1): "below it",
        (1, -1): "to its upper-right",
        (-1, -1): "to its upper-left",
        (1, 1): "to its lower-right",
        (-1, 1): "to its lower-left",
    }
    return table[(horizontal, vertical)]


def _sign(value: int) -> int:
    """Return -1, 0, or 1."""
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _nearest_others(obj: SceneObject, scene: tuple[SceneObject, ...]) -> list[SceneObject]:
    """Return up to ``_MAX_RELATIONS`` nearest other objects by Chebyshev distance."""
    others = [other for other in scene if other != obj]
    others.sort(
        key=lambda other: (
            max(abs(other.column - obj.column), abs(other.row - obj.row)),
            other.row,
            other.column,
        )
    )
    return others[:_MAX_RELATIONS]


def position_phrase(obj: SceneObject, scene: tuple[SceneObject, ...], grid_size: int) -> str:
    """Render an object's position as ``in the <region>[, with <relations>]``."""
    region = region_of(column=obj.column, row=obj.row, grid_size=grid_size)
    relations = [
        f"a {describe_bundle(obj=other)} {_direction_phrase(from_obj=obj, to_obj=other)}"
        for other in _nearest_others(obj=obj, scene=scene)
    ]
    if not relations:
        return f"in the {region}"
    return f"in the {region}, with {' and '.join(relations)}"


def render_object_relational(
    obj: SceneObject, scene: tuple[SceneObject, ...], grid_size: int
) -> str:
    """Render one object as ``a <bundle> <position phrase>``."""
    return (
        f"a {describe_bundle(obj=obj)} {position_phrase(obj=obj, scene=scene, grid_size=grid_size)}"
    )


def render_scene_relational(scene: tuple[SceneObject, ...], grid_size: int) -> list[str]:
    """Render a scene's objects in reading order (top-to-bottom, left-to-right)."""
    ordered = sorted(scene, key=lambda obj: (obj.row, obj.column))
    return [render_object_relational(obj=obj, scene=scene, grid_size=grid_size) for obj in ordered]


def describe_difference(
    difference: PlantedDifference,
    scene_a: tuple[SceneObject, ...],
    scene_b: tuple[SceneObject, ...],
    grid_size: int,
) -> str:
    """Build the canonical relational ground-truth phrasing for one difference."""
    if difference.kind == DifferenceKind.ATTRIBUTE_CHANGED:
        a = difference.scene_a_object
        b = difference.scene_b_object
        assert a is not None and b is not None and difference.attribute_name is not None
        attr = difference.attribute_name
        rendered = render_object_relational(obj=a, scene=scene_a, grid_size=grid_size)
        return (
            f"Attribute change: {rendered} has a different {attr} in the two scenes "
            f"({getattr(a, attr)} versus {getattr(b, attr)})."
        )
    if difference.kind == DifferenceKind.OBJECT_MOVED:
        a = difference.scene_a_object
        b = difference.scene_b_object
        assert a is not None and b is not None
        return (
            f"Position change: a {describe_bundle(obj=a)} is "
            f"{position_phrase(obj=a, scene=scene_a, grid_size=grid_size)} in one scene but "
            f"{position_phrase(obj=b, scene=scene_b, grid_size=grid_size)} in the other."
        )
    if difference.kind == DifferenceKind.OBJECT_ADDED:
        b = difference.scene_b_object
        assert b is not None
        return (
            f"Extra object: {render_object_relational(obj=b, scene=scene_b, grid_size=grid_size)} "
            f"appears in only one of the two scenes."
        )
    a = difference.scene_a_object
    assert a is not None
    return (
        f"Missing object: {render_object_relational(obj=a, scene=scene_a, grid_size=grid_size)} "
        f"appears in only one of the two scenes."
    )


def get_cases(
    seed: int,
    round_count: int,
    grid_size: int,
    round_time_budget_seconds: int,
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
                round_time_budget_seconds=round_time_budget_seconds,
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
    round_time_budget_seconds: int,
    object_count: int,
    difference_count: int,
    kinds: list[DifferenceKind],
) -> DiffCase:
    """Build scene A, plant ``difference_count`` isolated edits to form scene B."""
    all_cells = [
        (column, row) for column in range(1, grid_size + 1) for row in range(1, grid_size + 1)
    ]
    chosen_cells = rng.sample(all_cells, k=object_count)
    scene_a: list[SceneObject] = [
        SceneObject(
            shape=rng.choice(SHAPES),
            color=rng.choice(COLORS),
            size=rng.choice(SIZES),
            column=column,
            row=row,
        )
        for column, row in chosen_cells
    ]
    builder = _SceneBBuilder(scene_a=scene_a, all_cells=all_cells, grid_size=grid_size)
    drawn_kinds = [rng.choice(kinds) for _ in range(difference_count)]
    raw_differences = [builder.apply_edit(rng=rng, kind=kind) for kind in drawn_kinds]
    scene_b = tuple(builder.finalize())
    scene_a_tuple = tuple(scene_a)
    differences = tuple(
        raw._replace(
            description=describe_difference(
                difference=raw,
                scene_a=scene_a_tuple,
                scene_b=scene_b,
                grid_size=grid_size,
            )
        )
        for raw in raw_differences
    )
    return DiffCase(
        case_number=case_number,
        grid_size=grid_size,
        round_time_budget_seconds=round_time_budget_seconds,
        difference_count=difference_count,
        scene_a=scene_a_tuple,
        scene_b=scene_b,
        differences=differences,
    )


class _SceneBBuilder:
    """Mutates a copy of scene A into scene B by applying isolated edits.

    Each edit consumes a distinct object index (attribute change, move,
    remove) or only a fresh cell (add), reserving cells so no two edits
    interact. ``object_moved`` always relocates to a different region.
    """

    def __init__(
        self, scene_a: list[SceneObject], all_cells: list[tuple[int, int]], grid_size: int
    ) -> None:
        self._scene_a = scene_a
        self._all_cells = all_cells
        self._grid_size = grid_size
        self._b_objects: list[SceneObject | None] = list(scene_a)
        self._added: list[SceneObject] = []
        self._locked_indices: set[int] = set()
        self._occupied_cells: set[tuple[int, int]] = {(obj.column, obj.row) for obj in scene_a}

    def finalize(self) -> list[SceneObject]:
        """Return scene B as the surviving original objects plus added objects."""
        survivors = [obj for obj in self._b_objects if obj is not None]
        return survivors + self._added

    def apply_edit(self, rng: random.Random, kind: DifferenceKind) -> PlantedDifference:
        """Apply one edit of ``kind``; returns the difference with description still blank."""
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

    def _pick_empty_cell(self, rng: random.Random, exclude_region: str | None) -> tuple[int, int]:
        """Return a random cell empty in both scenes (optionally outside ``exclude_region``)."""
        empty = [cell for cell in self._all_cells if cell not in self._occupied_cells]
        if exclude_region is not None:
            empty = [
                cell
                for cell in empty
                if region_of(column=cell[0], row=cell[1], grid_size=self._grid_size)
                != exclude_region
            ]
        cell = rng.choice(empty)
        self._occupied_cells.add(cell)
        return cell

    def _apply_attribute_change(self, rng: random.Random) -> PlantedDifference:
        """Change one attribute of a fresh object to a different value."""
        index = self._pick_unlocked_index(rng=rng)
        original = self._scene_a[index]
        attribute_name = rng.choice(_ATTRIBUTE_NAMES)
        choices = [
            value
            for value in _VALUES_BY_ATTRIBUTE[attribute_name]
            if value != getattr(original, attribute_name)
        ]
        changed = original._replace(**{attribute_name: rng.choice(choices)})
        self._b_objects[index] = changed
        return PlantedDifference(
            kind=DifferenceKind.ATTRIBUTE_CHANGED,
            description="",
            scene_a_object=original,
            scene_b_object=changed,
            attribute_name=attribute_name,
        )

    def _apply_move(self, rng: random.Random) -> PlantedDifference:
        """Relocate a fresh object to a cell in a different region, empty in both scenes."""
        index = self._pick_unlocked_index(rng=rng)
        original = self._scene_a[index]
        origin_region = region_of(
            column=original.column, row=original.row, grid_size=self._grid_size
        )
        column, row = self._pick_empty_cell(rng=rng, exclude_region=origin_region)
        moved = original._replace(column=column, row=row)
        self._b_objects[index] = moved
        return PlantedDifference(
            kind=DifferenceKind.OBJECT_MOVED,
            description="",
            scene_a_object=original,
            scene_b_object=moved,
            attribute_name=None,
        )

    def _apply_add(self, rng: random.Random) -> PlantedDifference:
        """Add a new object to scene B at a fresh cell."""
        column, row = self._pick_empty_cell(rng=rng, exclude_region=None)
        added = SceneObject(
            shape=rng.choice(SHAPES),
            color=rng.choice(COLORS),
            size=rng.choice(SIZES),
            column=column,
            row=row,
        )
        self._added.append(added)
        return PlantedDifference(
            kind=DifferenceKind.OBJECT_ADDED,
            description="",
            scene_a_object=None,
            scene_b_object=added,
            attribute_name=None,
        )

    def _apply_remove(self, rng: random.Random) -> PlantedDifference:
        """Remove a fresh object from scene B (present in A, absent from B)."""
        index = self._pick_unlocked_index(rng=rng)
        original = self._scene_a[index]
        self._b_objects[index] = None
        return PlantedDifference(
            kind=DifferenceKind.OBJECT_REMOVED,
            description="",
            scene_a_object=original,
            scene_b_object=None,
            attribute_name=None,
        )
