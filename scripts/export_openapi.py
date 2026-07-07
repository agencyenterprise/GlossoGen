"""Export the FastAPI OpenAPI schema to stdout as JSON.

Used by ``make gen-api-types`` to produce the frontend type definitions.
"""

import json
import os

# The MCP consent/whoami routes are only mounted when OAUTH_ISSUER_URL is set
# (see glossogen.server.app). Pin it here so the exported schema always includes
# the full MCP surface regardless of the caller's environment, keeping the
# generated frontend types deterministic. app.py reads OAUTH_ISSUER_URL at
# import time, so this must run before importing app.
os.environ.setdefault("OAUTH_ISSUER_URL", "http://localhost:8000")
os.environ.setdefault("GLOSSOGEN_RUNS_DIR", "./runs")

from glossogen.server.app import app

if __name__ == "__main__":
    schema = app.openapi()
    print(json.dumps(obj=schema, indent=2))
