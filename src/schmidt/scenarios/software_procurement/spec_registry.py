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


def list_available_spec_names() -> list[str]:
    """Return all available software spec names from the specs directory."""
    return sorted(spec_file.stem for spec_file in SPECS_DIR.glob("*.json") if spec_file.is_file())


def load_spec(spec_name: str, include_impossible: bool) -> SoftwareSpec:
    """Load a spec by name and optionally remove the impossible requirement."""
    normalized_spec_name = spec_name.strip()
    available_spec_names = list_available_spec_names()

    if normalized_spec_name == "":
        raise ValueError("spec_name must be a non-empty string")

    if normalized_spec_name not in available_spec_names:
        raise ValueError(
            f"Unknown spec_name '{spec_name}'. "
            f"Available specs: {', '.join(available_spec_names)}"
        )

    spec_path = SPECS_DIR / f"{normalized_spec_name}.json"
    with spec_path.open(mode="r", encoding="utf-8") as spec_file:
        data = json.load(spec_file)

    if not include_impossible:
        data["impossible_requirement"] = ""

    return SoftwareSpec(**data)
