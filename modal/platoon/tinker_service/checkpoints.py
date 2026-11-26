"""Where the service keeps checkpoints, and the ``tinker://`` paths that name them.

A path is ``tinker://<model id>/weights/<name>`` for a full checkpoint (the adapter and its
optimizer state), or ``tinker://<model id>/sampler_weights/<name>`` for an adapter that the sampler
loads. Each one is a folder ``<root>/<model id>/<kind>/<name>/`` that also holds
``adapter_info.json``, the base model and the LoRA rank, so that a new run can start from a
checkpoint of an earlier one.
"""

import json
import logging
import shutil
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple

from tinker_service.records import AdapterInfo

logger = logging.getLogger(__name__)

SCHEME = "tinker://"
INFO_FILE = "adapter_info.json"


class CheckpointKind(StrEnum):
    """A full checkpoint, or the adapter alone that the sampler loads."""

    WEIGHTS = "weights"
    SAMPLER = "sampler_weights"


class CheckpointPath(NamedTuple):
    """The parts of a ``tinker://`` path."""

    model_id: str
    kind: CheckpointKind
    name: str


def parse_path(*, path: str) -> CheckpointPath:
    """The parts of ``path``; refuse a path that is not ``tinker://<model id>/<kind>/<name>``."""
    if not path.startswith(SCHEME):
        raise ValueError(f"{path!r} is not a tinker:// path")
    parts = path.removeprefix(SCHEME).split("/")
    if len(parts) != 3 or not all(parts):
        raise ValueError(f"{path!r} is not tinker://<model id>/<kind>/<name>")
    return CheckpointPath(model_id=parts[0], kind=CheckpointKind(parts[1]), name=parts[2])


def tinker_path(*, checkpoint: CheckpointPath) -> str:
    """The ``tinker://`` path of ``checkpoint``."""
    return f"{SCHEME}{checkpoint.model_id}/{checkpoint.kind.value}/{checkpoint.name}"


class CheckpointStore:
    """The checkpoint folders under one root."""

    def __init__(self, *, root: Path) -> None:
        self.root = root

    def folder(self, *, checkpoint: CheckpointPath) -> Path:
        """The folder of ``checkpoint``; a name may not leave its kind's folder."""
        if "/" in checkpoint.name or checkpoint.name in {".", ".."}:
            raise ValueError(f"checkpoint name {checkpoint.name!r} is not a plain name")
        return self.root / checkpoint.model_id / checkpoint.kind.value / checkpoint.name

    def write_info(self, *, checkpoint: CheckpointPath, info: AdapterInfo) -> None:
        """Record the checkpoint's base model and rank in its folder."""
        path = self.folder(checkpoint=checkpoint) / INFO_FILE
        path.write_text(json.dumps(info._asdict()) + "\n")

    def read_info(self, *, checkpoint: CheckpointPath) -> AdapterInfo:
        """The base model and rank that the checkpoint's folder records."""
        path = self.folder(checkpoint=checkpoint) / INFO_FILE
        if not path.exists():
            raise ValueError(f"no checkpoint at {tinker_path(checkpoint=checkpoint)}")
        return AdapterInfo(**json.loads(path.read_text()))

    def delete(self, *, checkpoint: CheckpointPath) -> None:
        """Remove the checkpoint's folder."""
        folder = self.folder(checkpoint=checkpoint)
        if not folder.exists():
            raise ValueError(f"no checkpoint at {tinker_path(checkpoint=checkpoint)}")
        shutil.rmtree(folder)
        logger.info("deleted %s", tinker_path(checkpoint=checkpoint))
