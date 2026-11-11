"""What the package cycle check reports when the cycles differ from the baseline.

The comparison is the part that can pass by accident: a new cycle, a package that
joins a cycle, a cycle that loses a member and a cycle that disappears each need
their own verdict. The graph helpers are checked on small hand-made graphs.
"""

from linter.check_package_cycles import (
    ProblemKind,
    collapse_edges,
    collapse_module,
    compare_cycles,
    find_cycles,
)


def test_a_cycle_equal_to_the_baseline_is_unchanged() -> None:
    cycles = [("a", "b", "c")]

    assert compare_cycles(baseline=cycles, current=cycles) == []


def test_no_cycles_and_an_empty_baseline_is_unchanged() -> None:
    assert compare_cycles(baseline=[], current=[]) == []


def test_a_cycle_between_unrelated_packages_is_new() -> None:
    problems = compare_cycles(baseline=[("a", "b")], current=[("a", "b"), ("x", "y")])

    assert [problem.kind for problem in problems] == [ProblemKind.NEW_CYCLE]
    assert problems[0].cycle == ("x", "y")


def test_a_package_joining_a_baseline_cycle_is_a_grown_cycle() -> None:
    problems = compare_cycles(baseline=[("a", "b")], current=[("a", "b", "c")])

    kinds = {problem.kind for problem in problems}
    assert ProblemKind.GROWN_CYCLE in kinds


def test_two_baseline_cycles_merging_is_a_grown_cycle() -> None:
    problems = compare_cycles(baseline=[("a", "b"), ("c", "d")], current=[("a", "b", "c", "d")])

    assert ProblemKind.GROWN_CYCLE in {problem.kind for problem in problems}


def test_a_cycle_that_loses_a_member_asks_for_a_smaller_baseline() -> None:
    problems = compare_cycles(baseline=[("a", "b", "c")], current=[("a", "b")])

    assert [problem.kind for problem in problems] == [ProblemKind.SHRUNK_CYCLE]
    assert "Shrink the baseline" in problems[0].message


def test_a_cycle_that_splits_asks_for_a_smaller_baseline() -> None:
    problems = compare_cycles(baseline=[("a", "b", "c", "d")], current=[("a", "b"), ("c", "d")])

    assert [problem.kind for problem in problems] == [ProblemKind.SHRUNK_CYCLE]


def test_a_cycle_that_disappears_asks_for_a_smaller_baseline() -> None:
    problems = compare_cycles(baseline=[("a", "b")], current=[])

    assert [problem.kind for problem in problems] == [ProblemKind.SHRUNK_CYCLE]
    assert problems[0].cycle == ("a", "b")


def test_scenario_submodules_are_their_own_nodes() -> None:
    assert collapse_module(module="glossogen.scenarios.veyru.knobs") == "scenarios.veyru"
    assert collapse_module(module="glossogen.scenarios.base_knobs") == "scenarios.base_knobs"
    assert collapse_module(module="glossogen.runtime.supervisor") == "runtime"
    assert collapse_module(module="glossogen.scenario_base") == "scenario_base"


def test_the_root_and_the_empty_scenarios_package_have_no_node() -> None:
    assert collapse_module(module="glossogen") is None
    assert collapse_module(module="glossogen.scenarios") is None
    assert collapse_module(module="other.package") is None


def test_importing_the_empty_scenarios_package_adds_no_edge() -> None:
    adjacency = collapse_edges(
        module_edges={
            ("glossogen.models.event", "glossogen.scenarios"),
            ("glossogen.scenarios", "glossogen.models.event"),
        }
    )

    assert adjacency["models"] == set()


def test_edges_inside_one_package_are_not_cycles() -> None:
    module_edges: set[tuple[str, str]] = {
        ("glossogen.runtime.a", "glossogen.runtime.b"),
        ("glossogen.runtime.b", "glossogen.runtime.a"),
    }
    adjacency = collapse_edges(module_edges=module_edges)

    assert find_cycles(adjacency=adjacency) == []


def test_find_cycles_returns_each_component_of_two_or_more_nodes() -> None:
    adjacency: dict[str, set[str]] = {
        "a": {"b"},
        "b": {"a", "c"},
        "c": {"d"},
        "d": {"e"},
        "e": {"d"},
        "f": set(),
    }

    assert find_cycles(adjacency=adjacency) == [("a", "b"), ("d", "e")]
