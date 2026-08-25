"""Label descriptions as one JSON file per group under the runs directory.

This is what a checkout with no ``DATABASE_URL`` uses. The glossary sits beside the
runs it describes, which means a runs directory copied to another machine carries its
label meanings with it.

The whole group's glossary is one file rather than one file per label, because a label
is an arbitrary string (``src=veyru/1777638061`` carries a path separator) and so
cannot be a filename. The file is written to a temporary name and renamed into place,
so a reader never sees a half-written glossary and a crashed write leaves the previous
version intact.

The group id is part of the path rather than a field inside the file. A read therefore
cannot return another group's glossary even if a file were mislabelled. A file that no
longer parses raises rather than reading as empty: an empty glossary and a broken one
are different answers, and saying so is the only way anyone finds out.
"""

import asyncio
from pathlib import Path
from uuid import UUID

import aiofiles
import orjson
from pydantic import BaseModel

from glossogen.label_descriptions.label_description_models import LabelDescription
from glossogen.label_descriptions.label_description_store import LabelDescriptionStore

LABEL_DESCRIPTION_DIR_NAME = "_label_descriptions"


class LabelDescriptionFile(BaseModel):
    """The on-disk shape of one group's glossary."""

    descriptions: list[LabelDescription]


class FilesystemLabelDescriptionStore(LabelDescriptionStore):
    """Label descriptions stored as one JSON file per group, under the runs directory."""

    def __init__(self, runs_dir: Path) -> None:
        self._runs_dir = runs_dir

    def _path_of(self, group_id: UUID) -> Path:
        """Return where one group's glossary lives."""
        return self._runs_dir / LABEL_DESCRIPTION_DIR_NAME / f"{group_id}.json"

    async def _read(self, group_id: UUID) -> list[LabelDescription]:
        """Read one group's glossary, empty when the group has never recorded one."""
        path = self._path_of(group_id=group_id)
        if not path.is_file():
            return []
        async with aiofiles.open(path, mode="rb") as handle:
            raw = await handle.read()
        return LabelDescriptionFile.model_validate(orjson.loads(raw)).descriptions

    async def _write(self, group_id: UUID, descriptions: list[LabelDescription]) -> None:
        """Write one group's glossary, replacing any previous version atomically."""
        path = self._path_of(group_id=group_id)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        pending = path.with_suffix(".json.pending")
        stored = LabelDescriptionFile(descriptions=descriptions)
        async with aiofiles.open(pending, mode="wb") as handle:
            await handle.write(stored.model_dump_json(indent=2).encode("utf-8"))
        await asyncio.to_thread(pending.replace, path)

    async def list_descriptions(self, group_id: UUID) -> list[LabelDescription]:
        """Return the group's label descriptions, sorted by label."""
        descriptions = await self._read(group_id=group_id)
        descriptions.sort(key=lambda entry: entry.label)
        return descriptions

    async def set_description(self, group_id: UUID, entry: LabelDescription) -> None:
        """Record what a label means, replacing any previous description of it."""
        others = [
            existing
            for existing in await self._read(group_id=group_id)
            if existing.label != entry.label
        ]
        await self._write(group_id=group_id, descriptions=[*others, entry])

    async def delete_description(self, group_id: UUID, label: str) -> bool:
        """Remove a label's description, returning whether one was there to remove."""
        descriptions = await self._read(group_id=group_id)
        remaining = [entry for entry in descriptions if entry.label != label]
        if len(remaining) == len(descriptions):
            return False
        await self._write(group_id=group_id, descriptions=remaining)
        return True
