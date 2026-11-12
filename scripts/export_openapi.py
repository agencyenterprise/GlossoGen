"""Export the FastAPI OpenAPI schema to stdout as JSON.

Used by ``make gen-api-types`` to produce the frontend type definitions. The app
is built here rather than imported from ``glossogen.server.app`` so the route set
depends only on this repository, never on the caller's environment or venv.
For the same reason it loads the built-in scenario catalog, so the schema
describes the scenarios shipped here.
"""

import json
import os

from fastapi import FastAPI

from glossogen.scenario_contract.catalog import built_in_scenario_sources, load_scenario_catalog
from glossogen.server.app_factory import create_app
from glossogen.server.server_runtime_config import load_server_runtime_config

# The MCP consent and whoami routes are mounted only when OAUTH_ISSUER_URL is
# set, so it is pinned to keep the exported schema covering the full MCP surface.
_EXPORT_OAUTH_ISSUER_URL = "http://localhost:8000"

# No identity provider, rather than whichever one the caller happens to have
# installed. A provider contributes routers, so resolving one here would let a
# developer's venv decide what lands in the committed schema and the
# check-api-types job would then fail for everyone else.
_EXPORT_IDENTITY_PROVIDER = None


def build_export_app() -> FastAPI:
    """Build an app whose route set and scenarios are a property of this repository alone."""
    os.environ.setdefault("OAUTH_ISSUER_URL", _EXPORT_OAUTH_ISSUER_URL)
    os.environ.setdefault("GLOSSOGEN_RUNS_DIR", "./runs")
    load_scenario_catalog(sources=built_in_scenario_sources())
    return create_app(
        identity_provider=_EXPORT_IDENTITY_PROVIDER,
        runtime_config=load_server_runtime_config(),
    )


if __name__ == "__main__":
    print(json.dumps(obj=build_export_app().openapi(), indent=2))
