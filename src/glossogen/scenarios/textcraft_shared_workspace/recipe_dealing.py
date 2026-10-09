"""Deal a pool task's recipes so each crafter holds only part of them.

Each recipe goes to ``holders`` distinct seats, chosen so the hands stay as even
as possible. The deal depends only on the task, the seats and ``holders``, so the
same task is dealt the same way in every arm and on every rerun.
"""

import random

from glossogen.scenarios.textcraft_shared_workspace.tasks import WorkspaceTask


def deal_recipes(task: WorkspaceTask, seats: list[str], holders: int) -> dict[str, list[str]]:
    """Each seat's recipe commands, sorted; every recipe is in exactly ``holders`` hands."""
    if not 1 <= holders <= len(seats):
        raise ValueError("holders must lie between 1 and the number of seats")
    rng = random.Random(f"{task.task_id}/{holders}/{len(seats)}")
    commands = sorted(recipe.command for recipe in task.recipes)
    rng.shuffle(commands)
    hands: dict[str, list[str]] = {seat: [] for seat in seats}
    for command in commands:
        order = list(seats)
        rng.shuffle(order)
        # Stable sort: the emptiest hands first, ties in the shuffled order.
        order.sort(key=lambda seat: len(hands[seat]))
        for seat in order[:holders]:
            hands[seat].append(command)
    return {seat: sorted(hand) for seat, hand in hands.items()}
