"""Budget tracking model for the product launch scenario.

Tracks total resource units (RU), per-round spending, and remaining budget.
"""

from pydantic import BaseModel


class BudgetEntry(BaseModel):
    """A single round's spending record.

    Attributes:
        round_number: The round in which spending occurred.
        amount_spent: Resource units consumed this round.
        category: What the spend was for (e.g. ``backend_effort``, ``qa_testing``).
    """

    round_number: int
    amount_spent: float
    category: str


class BudgetTracker(BaseModel):
    """Tracks budget allocation and spending across the simulation.

    Attributes:
        total_budget_ru: Total resource units available for the project.
        spent_ru: Total resource units spent so far.
        entries: Chronological list of spending records.
    """

    total_budget_ru: float
    spent_ru: float
    entries: list[BudgetEntry]

    def remaining_ru(self) -> float:
        """Return the remaining unspent resource units."""
        return self.total_budget_ru - self.spent_ru

    def record_spend(self, round_number: int, amount: float, category: str) -> None:
        """Record a spending event and update the running total."""
        self.entries.append(
            BudgetEntry(
                round_number=round_number,
                amount_spent=amount,
                category=category,
            )
        )
        self.spent_ru += amount
