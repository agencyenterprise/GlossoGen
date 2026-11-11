#!/usr/bin/env python3
"""
Fail when the package import graph gains a cycle or a package joins one.

The script builds the module-level import graph of ``glossogen`` with ``grimp``,
collapses it to top-level packages and finds the strongly connected components.
Each ``glossogen.scenarios.<name>`` counts as its own node, and the empty
``glossogen.scenarios`` package module is ignored so it adds no edges. A component
of two or more nodes is a cycle.

The cycles that exist today are listed in a baseline file. The check fails when
the current cycles are not exactly the baseline:

- a cycle that is not inside any baseline cycle is new, or a package joined one;
- a baseline cycle that lost members, split or disappeared means the baseline is
  stale and has to shrink. The baseline only ever gets smaller.

``--write-baseline`` rewrites the baseline from the current graph. Use it to
shrink the file after removing a cycle, never to admit a new one.
"""

import argparse
import json
import sys
from enum import Enum
from pathlib import Path
from typing import NamedTuple

import grimp

ROOT_PACKAGE = "glossogen"
SCENARIOS_PACKAGE = "scenarios"


class ProblemKind(str, Enum):
    """The ways the current cycles can differ from the baseline."""

    NEW_CYCLE = "new_cycle"
    GROWN_CYCLE = "grown_cycle"
    SHRUNK_CYCLE = "shrunk_cycle"


class CycleProblem(NamedTuple):
    """One difference between the current cycles and the baseline."""

    kind: ProblemKind
    cycle: tuple[str, ...]
    message: str


def collapse_module(module: str) -> str | None:
    """Return the package node a module belongs to, or None when it has none.

    The root package module and the ``glossogen.scenarios`` package module belong
    to no node. A module under ``glossogen.scenarios`` belongs to the node named
    after its first path part below it; any other module belongs to its top-level
    package or module.
    """
    parts = module.split(".")
    if parts[0] != ROOT_PACKAGE:
        return None
    if len(parts) == 1:
        return None
    if parts[1] == SCENARIOS_PACKAGE:
        if len(parts) == 2:
            return None
        return f"{SCENARIOS_PACKAGE}.{parts[2]}"
    return parts[1]


def collapse_edges(module_edges: set[tuple[str, str]]) -> dict[str, set[str]]:
    """Collapse module-to-module imports into a package-level adjacency map.

    Self edges and edges touching a module with no node are dropped.
    """
    adjacency: dict[str, set[str]] = {}
    for importer, imported in module_edges:
        source = collapse_module(module=importer)
        target = collapse_module(module=imported)
        if source is None or target is None:
            continue
        adjacency.setdefault(source, set())
        adjacency.setdefault(target, set())
        if source != target:
            adjacency[source].add(target)
    return adjacency


def find_cycles(adjacency: dict[str, set[str]]) -> list[tuple[str, ...]]:
    """Return the strongly connected components of two or more nodes, sorted.

    Tarjan's algorithm. Each component is a sorted tuple of node names and the
    list is sorted, so the result compares equal across runs.
    """
    index_of: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[tuple[str, ...]] = []
    counter = 0

    def visit(node: str) -> None:
        nonlocal counter
        index_of[node] = counter
        lowlink[node] = counter
        counter += 1
        stack.append(node)
        on_stack.add(node)
        for neighbour in sorted(adjacency.get(node, set())):
            if neighbour not in index_of:
                visit(node=neighbour)
                lowlink[node] = min(lowlink[node], lowlink[neighbour])
            elif neighbour in on_stack:
                lowlink[node] = min(lowlink[node], index_of[neighbour])
        if lowlink[node] != index_of[node]:
            return
        members: list[str] = []
        while True:
            member = stack.pop()
            on_stack.discard(member)
            members.append(member)
            if member == node:
                break
        if len(members) > 1:
            components.append(tuple(sorted(members)))

    for node in sorted(adjacency):
        if node not in index_of:
            visit(node=node)
    return sorted(components)


def compare_cycles(
    baseline: list[tuple[str, ...]], current: list[tuple[str, ...]]
) -> list[CycleProblem]:
    """Compare the current cycles with the baseline and list every difference.

    A current cycle inside no baseline cycle is new when it shares no package with
    the baseline and grown when it does. A baseline cycle that the current cycles
    do not reproduce exactly (fewer members, split, or gone) is shrunk. An empty
    result means the two match.
    """
    problems: list[CycleProblem] = []
    baseline_sets = [set(cycle) for cycle in baseline]
    all_baseline_nodes: set[str] = set()
    for members in baseline_sets:
        all_baseline_nodes |= members

    for cycle in current:
        members = set(cycle)
        if any(members <= allowed for allowed in baseline_sets):
            continue
        if members & all_baseline_nodes:
            problems.append(
                CycleProblem(
                    kind=ProblemKind.GROWN_CYCLE,
                    cycle=cycle,
                    message=(
                        f"a package joined an existing cycle: {', '.join(cycle)}. "
                        "Remove the import that closes it."
                    ),
                )
            )
        else:
            problems.append(
                CycleProblem(
                    kind=ProblemKind.NEW_CYCLE,
                    cycle=cycle,
                    message=(
                        f"new package cycle: {', '.join(cycle)}. "
                        "Remove the import that closes it."
                    ),
                )
            )

    for cycle, members in zip(baseline, baseline_sets):
        inside = [set(found) for found in current if set(found) <= members]
        if len(inside) == 1 and inside[0] == members:
            continue
        problems.append(
            CycleProblem(
                kind=ProblemKind.SHRUNK_CYCLE,
                cycle=cycle,
                message=(
                    f"the baseline cycle {', '.join(cycle)} no longer exists as written. "
                    "Shrink the baseline: run this script with --write-baseline and commit "
                    "the result."
                ),
            )
        )
    return problems


def read_baseline(path: Path) -> list[tuple[str, ...]]:
    """Read the baseline file: a JSON list of lists of package names."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return sorted(tuple(sorted(cycle)) for cycle in raw)


def write_baseline(path: Path, cycles: list[tuple[str, ...]]) -> None:
    """Write the cycles to the baseline file, one cycle per list."""
    path.write_text(
        json.dumps([list(cycle) for cycle in cycles], indent=2) + "\n", encoding="utf-8"
    )


def build_module_edges() -> set[tuple[str, str]]:
    """Return every (importer, imported) module pair inside ``glossogen``."""
    graph = grimp.build_graph(ROOT_PACKAGE)
    edges: set[tuple[str, str]] = set()
    for module in graph.modules:
        for imported in graph.find_modules_directly_imported_by(module):
            edges.add((module, imported))
    return edges


def main() -> int:
    """Check the current cycles against the baseline and print the differences."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--write-baseline", action="store_true")
    arguments = parser.parse_args()

    current = find_cycles(adjacency=collapse_edges(module_edges=build_module_edges()))
    if arguments.write_baseline:
        write_baseline(path=arguments.baseline, cycles=current)
        print(f"Wrote {len(current)} cycle(s) to {arguments.baseline}")
        return 0

    problems = compare_cycles(baseline=read_baseline(path=arguments.baseline), current=current)
    for problem in problems:
        print(f"{problem.kind.value}: {problem.message}")
    if problems:
        return 1
    print(f"Package cycles match the baseline ({len(current)} cycle(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
