"""Sanity-check spot_the_difference scene generation.

Asserts determinism (same seed -> identical cases), that applying the K
planted edits to scene A reproduces scene B exactly, that duplicate bundles
occur at the configured scene sizes, that every ``object_moved`` crosses a
region, that each difference carries a relational description, and that easy
rounds collapse to K=1. Run directly:

    VIRTUAL_ENV= uv run --no-sync python -m \
      schmidt.scenarios.spot_the_difference.scripts.check_scene_generation
"""

from schmidt.scenarios.spot_the_difference.ids import DifferenceKind
from schmidt.scenarios.spot_the_difference.scene_generation import (
    DiffCase,
    SceneObject,
    get_cases,
    region_of,
    render_scene_relational,
)

_KINDS = [kind.value for kind in DifferenceKind]


def _cell(obj: SceneObject) -> tuple[int, int]:
    return (obj.column, obj.row)


def _reconstruct_scene_b(case: DiffCase) -> set[SceneObject]:
    """Apply the planted differences to scene A; the result must equal scene B."""
    objects = list(case.scene_a)
    for diff in case.differences:
        if diff.kind == DifferenceKind.OBJECT_ADDED:
            assert diff.scene_b_object is not None
            objects.append(diff.scene_b_object)
            continue
        assert diff.scene_a_object is not None, f"{diff.kind} missing scene_a_object"
        objects.remove(diff.scene_a_object)
        if diff.kind != DifferenceKind.OBJECT_REMOVED:
            assert diff.scene_b_object is not None
            objects.append(diff.scene_b_object)
    return set(objects)


def _assert_unique_cells(case: DiffCase) -> None:
    a_cells = [_cell(obj) for obj in case.scene_a]
    b_cells = [_cell(obj) for obj in case.scene_b]
    assert len(a_cells) == len(set(a_cells)), f"scene A duplicate cells in case {case.case_number}"
    assert len(b_cells) == len(set(b_cells)), f"scene B duplicate cells in case {case.case_number}"


def _has_duplicate_bundle(case: DiffCase) -> bool:
    bundles = [obj.bundle for obj in case.scene_a]
    return len(bundles) != len(set(bundles))


def _assert_moves_cross_region(case: DiffCase) -> None:
    for diff in case.differences:
        if diff.kind != DifferenceKind.OBJECT_MOVED:
            continue
        a = diff.scene_a_object
        b = diff.scene_b_object
        assert a is not None and b is not None
        region_a = region_of(column=a.column, row=a.row, grid_size=case.grid_size)
        region_b = region_of(column=b.column, row=b.row, grid_size=case.grid_size)
        assert (
            region_a != region_b
        ), f"case {case.case_number}: moved object stayed in region {region_a}"


def _generate() -> list[DiffCase]:
    """Generate the canonical batch used by every assertion."""
    return get_cases(
        seed=42,
        round_count=15,
        grid_size=12,
        round_time_budget_seconds=500,
        object_count_values=[12, 15, 18],
        object_count_weights=[1, 1, 1],
        difference_count_values=[2, 3, 4],
        difference_count_weights=[1, 1, 1],
        difference_kinds=_KINDS,
        easy_round_numbers=frozenset({1, 2, 3}),
    )


def main() -> None:
    """Generate two identical batches and validate every case."""
    cases_one = _generate()
    cases_two = _generate()
    assert cases_one == cases_two, "generation is not deterministic for a fixed seed"

    rounds_with_duplicates = 0
    for case in cases_one:
        _assert_unique_cells(case=case)
        _assert_moves_cross_region(case=case)
        planted = len(case.differences)
        assert planted == case.difference_count, (
            f"case {case.case_number}: planted {planted} != difference_count "
            f"{case.difference_count}"
        )
        assert _reconstruct_scene_b(case=case) == set(
            case.scene_b
        ), f"case {case.case_number}: planted differences do not reproduce scene B exactly"
        assert set(case.scene_a) != set(
            case.scene_b
        ), f"case {case.case_number}: scenes are identical"
        for diff in case.differences:
            assert diff.description, f"case {case.case_number}: empty description for {diff.kind}"
        if case.case_number in {1, 2, 3}:
            assert case.difference_count == 1, f"easy case {case.case_number} K != 1"
        if _has_duplicate_bundle(case=case):
            rounds_with_duplicates += 1

    assert (
        rounds_with_duplicates > 0
    ), "no round contained duplicate bundles; vocab/scene too sparse"
    kinds_seen = sorted({diff.kind.value for case in cases_one for diff in case.differences})
    print(
        f"OK: {len(cases_one)} cases, deterministic, kinds={kinds_seen}, "
        f"{rounds_with_duplicates}/{len(cases_one)} rounds with duplicate bundles"
    )
    sample = cases_one[3]
    print(f"--- sample round {sample.case_number} (K={sample.difference_count}) scene A ---")
    for line in render_scene_relational(scene=sample.scene_a, grid_size=sample.grid_size)[:5]:
        print(f"  {line}")
    print("--- planted differences ---")
    for diff in sample.differences:
        print(f"  [{diff.kind.value}] {diff.description}")


if __name__ == "__main__":
    main()
