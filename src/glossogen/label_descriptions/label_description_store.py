"""What a label-description store has to do, whichever thing is storing them.

Two implementations exist because the platform runs two ways, the same split the
dashboard store has. With a database the glossary lives beside the runs index, visible
to everyone in a group. Without one, a single-tenant checkout keeps it in the runs
directory, so the feature is not something only a deployment has.

Every method is scoped by ``group_id``. A store never sees a request, so there is no
path by which one group's glossary could be handed to another.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from glossogen.label_descriptions.label_description_models import LabelDescription


class LabelDescriptionStore(ABC):
    """Storage for one group's label descriptions."""

    @abstractmethod
    async def list_descriptions(self, group_id: UUID) -> list[LabelDescription]:
        """Return the group's label descriptions, sorted by label."""

    @abstractmethod
    async def set_description(self, group_id: UUID, entry: LabelDescription) -> None:
        """Record what a label means, replacing any previous description of it."""

    @abstractmethod
    async def delete_description(self, group_id: UUID, label: str) -> bool:
        """Remove a label's description, returning whether one was there to remove."""
