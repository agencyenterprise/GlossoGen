"""The server instance uvicorn imports.

Kept to a single construction so `glossogen.server.app:app` stays a stable
import string for `glossogen serve`, `make dev`, and the OpenAPI export. The
assembly itself lives in :mod:`glossogen.server.app_factory`.

`glossogen serve` has loaded the scenario catalog before uvicorn imports this
module. Run directly by uvicorn, as `make dev` does, this module loads the
built-in catalog itself.
"""

from glossogen.dotenv_loader import load_env_from_working_directory
from glossogen.scenario_contract.catalog import load_built_in_scenario_catalog_unless_loaded
from glossogen.server.app_factory import create_app
from glossogen.server.identity.identity_provider_loader import load_identity_provider
from glossogen.server.server_runtime_config import load_server_runtime_config

load_env_from_working_directory()
load_built_in_scenario_catalog_unless_loaded()
app = create_app(
    identity_provider=load_identity_provider(),
    runtime_config=load_server_runtime_config(),
)
