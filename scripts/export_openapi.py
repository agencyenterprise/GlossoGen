"""Export the FastAPI OpenAPI schema to stdout as JSON.

Used by ``make gen-api-types`` to produce the frontend type definitions.
"""

import json
import os

from schmidt.server.app import app

if __name__ == "__main__":
    os.environ.setdefault("SCHMIDT_RUNS_DIR", "./runs")
    schema = app.openapi()
    print(json.dumps(obj=schema, indent=2))
