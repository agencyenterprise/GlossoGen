"""Software specification definitions for procurement scenarios.

Each spec describes a product the buyer needs, with requirements the buyer
translates into an API contract and tests during the simulation.
"""

import json
from pathlib import Path

from pydantic import BaseModel

SPECS_DIR = Path(__file__).parent / "specs"


class SoftwareSpec(BaseModel):
    """A product specification fed to the buyer agent."""

    name: str
    description: str
    requirements: list[str]
    impossible_requirement: str


def load_spec(spec_name: str, include_impossible: bool) -> SoftwareSpec:
    """Load a spec JSON file by name and optionally include the impossible requirement."""
    spec_path = SPECS_DIR / f"{spec_name}.json"
    with spec_path.open() as f:
        data = json.load(f)

    if not include_impossible:
        data["impossible_requirement"] = ""

    return SoftwareSpec(**data)
