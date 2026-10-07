"""Atomic finite-depot transitions and per-observer snapshots/deltas."""

from collections import Counter, deque
from dataclasses import dataclass, field

from glossogen.scenarios.textcraft_shared_workspace.tasks import WorkspaceTask


@dataclass(eq=False)
class PendingCraft:
    """A craft whose inputs are consumed and whose output is still being made."""

    agent_id: str
    command: str
    output: str
    count: int
    consumed: list[tuple[str, str, int]]


@dataclass
class Transition:
    """Ground truth for a single attempt; provenance never enters observations."""

    command: str
    accepted: bool
    observation: str
    delta: dict[str, int] = field(default_factory=dict[str, int])
    consumed_from: list[tuple[str, str, int]] = field(default_factory=list[tuple[str, str, int]])
    pending: PendingCraft | None = None
    """A started craft whose output has not landed yet; ``DepotState.finish`` lands it."""


UNCRAFT_PREFIX = "uncraft "
"""Prefix that turns an exact crafting command into its reversal."""


def restore_lots(lots: deque[tuple[str, int]], restored: list[tuple[str, int]]) -> None:
    """Put lots back at the front, in their original order, merging equal producers."""
    for producer, quantity in reversed(restored):
        if lots and lots[0][0] == producer:
            quantity += lots.popleft()[1]
        lots.appendleft((producer, quantity))


class DepotState:
    """Every item is public state; there are no inventories or resource fetching."""

    def __init__(
        self,
        task: WorkspaceTask,
        seats: list[str],
        uncraft_enabled: bool,
    ) -> None:
        self.task = task
        self.seats = seats
        self.depot = Counter(task.initial_depot)
        self.version = 0
        self.changes: list[dict[str, int]] = []
        self.cursors = dict.fromkeys(seats, 0)
        self.recipes = {recipe.command: recipe for recipe in task.recipes}
        self.provenance: dict[str, deque[tuple[str, int]]] = {
            item: deque([("environment", count)]) for item, count in self.depot.items()
        }
        self.uncraft_enabled = uncraft_enabled
        # Per recipe command, the input lots each unreversed craft took, oldest first.
        self.live_crafts: dict[str, list[list[tuple[str, str, int]]]] = {}
        self.failed_crafts = 0
        # Started crafts whose output has not landed, in start order.
        self.in_progress: list[PendingCraft] = []

    @property
    def solved(self) -> bool:
        """Targets must coexist; historical completion is insufficient."""
        required = Counter(card.target for card in self.task.cards.values())
        return all(self.depot[item] >= count for item, count in required.items())

    def step(self, agent_id: str, command: str) -> Transition:
        """Validate the whole rewrite before consuming anything; all recipes usable."""
        return self._apply(agent_id=agent_id, command=command, defer_output=False)

    def start(self, agent_id: str, command: str) -> Transition:
        """Like ``step``, but an accepted craft takes its inputs without landing its output.

        The returned transition's ``pending`` goes to ``finish`` when the craft ends.
        """
        return self._apply(agent_id=agent_id, command=command, defer_output=True)

    def _apply(self, agent_id: str, command: str, defer_output: bool) -> Transition:
        """Run one command; ``defer_output`` holds an accepted craft's output back."""
        if agent_id not in self.seats:
            raise ValueError("unknown crafter")
        command = command.strip()
        if self.uncraft_enabled and command.startswith(UNCRAFT_PREFIX):
            return self.uncraft(command=command)
        recipe = self.recipes.get(command)
        if recipe is None:
            return Transition(
                command,
                False,
                "Invalid command. Use an exact crafting command.",
            )
        if any(self.depot[item] < count for item, count in recipe.inputs.items()):
            self.failed_crafts += 1
            # No missing-item names or counts: the failure says only that it failed.
            return Transition(command, False, "Craft failed: insufficient inputs.")
        consumed: list[tuple[str, str, int]] = []
        for item, count in recipe.inputs.items():
            remaining = count
            lots = self.provenance[item]
            while remaining:
                producer, quantity = lots.popleft()
                take = min(quantity, remaining)
                consumed.append((producer, item, take))
                if quantity > take:
                    lots.appendleft((producer, quantity - take))
                remaining -= take
        self.depot.subtract(recipe.inputs)
        delta = {item: -count for item, count in recipe.inputs.items()}
        if defer_output:
            pending = PendingCraft(
                agent_id=agent_id,
                command=command,
                output=recipe.output,
                count=recipe.count,
                consumed=consumed,
            )
            self.in_progress.append(pending)
            self.version += 1
            self.changes.append(delta)
            return Transition(
                command,
                True,
                f"Started crafting {recipe.count} {recipe.output}.",
                delta,
                consumed,
                pending,
            )
        self._land(agent_id=agent_id, output=recipe.output, count=recipe.count)
        self.live_crafts.setdefault(command, []).append(consumed)
        delta[recipe.output] = delta.get(recipe.output, 0) + recipe.count
        self.version += 1
        self.changes.append(delta)
        return Transition(
            command, True, f"Crafted {recipe.count} {recipe.output}.", delta, consumed
        )

    def _land(self, agent_id: str, output: str, count: int) -> None:
        """Add a craft's output to the depot, credited to the crafter."""
        self.depot[output] += count
        self.provenance.setdefault(output, deque()).append((agent_id, count))

    def finish(self, pending: PendingCraft) -> Transition:
        """Land a started craft's output; it becomes visible and uncraftable now."""
        self.in_progress.remove(pending)
        self._land(agent_id=pending.agent_id, output=pending.output, count=pending.count)
        self.live_crafts.setdefault(pending.command, []).append(pending.consumed)
        delta = {pending.output: pending.count}
        self.version += 1
        self.changes.append(delta)
        return Transition(
            pending.command, True, f"Crafted {pending.count} {pending.output}.", delta
        )

    def uncraft(self, command: str) -> Transition:
        """Reverse the most recent unreversed application of one recipe, one step only.

        The recipe's full output leaves the depot and its direct inputs return in
        full, credited back to the producers they came from; inputs that were
        themselves crafted are not broken down further. Output units leave last
        in, first out, so they are the ones the reversed application added
        whenever nothing has consumed them since.
        """
        recipe = self.recipes.get(command.removeprefix(UNCRAFT_PREFIX).strip())
        if recipe is None:
            return Transition(
                command,
                False,
                "Invalid command. Use 'uncraft ' followed by an exact crafting command.",
            )
        live = self.live_crafts.get(recipe.command, [])
        if not live or self.depot[recipe.output] < recipe.count:
            # One message for both causes, matching the failed-craft feedback.
            return Transition(command, False, "Uncraft failed: not enough crafted output.")
        consumed = live.pop()
        removed: list[tuple[str, str, int]] = []
        lots = self.provenance[recipe.output]
        remaining = recipe.count
        while remaining:
            producer, quantity = lots.pop()
            take = min(quantity, remaining)
            removed.append((producer, recipe.output, take))
            if quantity > take:
                lots.append((producer, quantity - take))
            remaining -= take
        for item in recipe.inputs:
            restore_lots(
                lots=self.provenance.setdefault(item, deque()),
                restored=[
                    (producer, take)
                    for producer, consumed_item, take in consumed
                    if consumed_item == item
                ],
            )
        self.depot[recipe.output] -= recipe.count
        self.depot.update(recipe.inputs)
        delta = dict(recipe.inputs)
        delta[recipe.output] = delta.get(recipe.output, 0) - recipe.count
        self.version += 1
        self.changes.append(delta)
        returned = ", ".join(f"{n} {item}" for item, n in sorted(recipe.inputs.items()))
        return Transition(
            command,
            True,
            f"Uncrafted {recipe.count} {recipe.output} back into {returned}.",
            delta,
            removed,
        )

    def observe(self, agent_id: str) -> str:
        """Current absolute quantities plus ordered changes, private cursor per agent."""
        since = self.cursors[agent_id]
        changes = self.changes[since:]
        self.cursors[agent_id] = self.version
        snapshot = ", ".join(f"{item}={count}" for item, count in sorted(self.depot.items()))
        lines = [f"Depot now (v{self.version}): {snapshot}", "Changes since your last observation:"]
        for version, delta in enumerate(changes, since + 1):
            lines.append(
                f"v{version}: " + ", ".join(f"{i} {n:+d}" for i, n in sorted(delta.items()))
            )
        if not changes:
            lines.append("none")
        if self.in_progress:
            making = ", ".join(f"{craft.count} {craft.output}" for craft in self.in_progress)
            lines.append(f"Being crafted now (inputs taken, output not in the depot yet): {making}")
        return "\n".join(lines)
