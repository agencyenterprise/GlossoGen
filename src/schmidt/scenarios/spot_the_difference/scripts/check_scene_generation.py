"""Sanity-check spot_the_difference scene generation.

Asserts determinism (same seed -> identical cases), that each case differs in
exactly K detectable ways, that planted differences are isolated (distinct
objects / cells), and that easy rounds collapse to K=1. Run directly:

    VIRTUAL_ENV= uv run --no-sync python -m \
      schmidt.scenarios.spot_the_difference.scripts.check_scene_generation
"""

from schmidt.scenarios.spot_the_difference.ids import DifferenceKind
from schmidt.scenarios.spot_the_difference.scene_generation import DiffCase, SceneObject, get_cases

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


def _generate() -> list[DiffCase]:
    """Generate the canonical 15-round batch used by every assertion."""
    return get_cases(
        seed=42,
        round_count=15,
        grid_size=8,
        object_count_values=[5, 6, 7],
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

    for case in cases_one:
        _assert_unique_cells(case=case)
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
        if case.case_number in {1, 2, 3}:
            assert case.difference_count == 1, f"easy case {case.case_number} K != 1"

    kinds_seen = sorted({diff.kind.value for case in cases_one for diff in case.differences})
    print(f"OK: {len(cases_one)} cases, deterministic, kinds exercised: {kinds_seen}")
    for case in cases_one[:5]:
        print(
            f"  round {case.case_number}: {len(case.scene_a)} objs, K={case.difference_count}, "
            f"kinds={[d.kind.value for d in case.differences]}"
        )


if __name__ == "__main__":
    main()
