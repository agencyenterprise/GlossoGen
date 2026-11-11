"""The run identifier, ``<scenario>/<run_dir_name>``, built from its two path components."""


def compose_run_id(scenario_name: str, run_dir_name: str) -> str:
    """Build the canonical ``<scenario>/<run_dir_name>`` identifier."""
    return f"{scenario_name}/{run_dir_name}"
