# Deployment

Two services: the FastAPI backend and the Next.js frontend. Either can be run from
a container image. The backend also needs Postgres and a volume for run data.

## Self-hosting with docker compose

The whole stack (Postgres, backend, frontend) in one command:

```bash
cp .env.example .env     # then set your provider API keys
docker compose up --build
```

Frontend on `http://localhost:3000`, backend on `http://localhost:8000`. Run data
persists in the `runs-data` volume, Postgres in `postgres-data`.

This runs in **single-tenant mode**: no identity provider, every request is `local-user`
in the `local` group. It performs no authentication, so do not expose it to the
internet without installing an identity provider first. See
[Authentication](authentication-and-frontend.md#authentication).

`API_URL` is read at request time, so pointing the frontend at a different backend
takes a restart rather than a rebuild.

## Images

| Service | Build file | Contents |
|---|---|---|
| Backend | `Dockerfile` | Python 3.14, FastAPI, weasyprint system libraries |
| Frontend | `frontend/DockerfileFrontend` | Node 22, Next.js standalone build |

`.github/workflows/publish-images.yml` builds both and pushes them to GHCR on a
version tag. Tags come from the release label on a merged pull request. See
[Releases](../CONTRIBUTING.md#releases). Each is a manifest list covering
`linux/amd64` and `linux/arm64`, so a pull resolves to the host's own
architecture: deployment targets are amd64 and development machines are often
arm64, and one image serves both. The two architectures are built on runners of
their own rather than cross-built under emulation, which is what keeps a release
from taking three times as long. Releases up to and including `v0.2.0` carry
amd64 only.

The backend image runs `alembic upgrade head` on every start, so the schema is at
the latest revision before the server accepts requests.

## Railway

The deployment target in use. The frontend is built from this repository and
carries `frontend/railway.toml`. The backend is deployed from the published image
and promoted by tag, so it has no config-as-code file here.

**Backend service**: root directory `/`, with a volume mounted at `/data/runs` and
a Railway Postgres attached.

| Variable | What it is |
|---|---|
| `DATABASE_URL` | Required. The attached Postgres connection string; the backend will not boot without it |
| Provider API keys | One per provider your runs use: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and so on. The shipped presets use an Anthropic judge wherever a scenario has one |
| `ALLOWED_ORIGINS` | Comma-separated frontend URLs, for CORS |
| whatever the installed identity provider reads | Required for multi-tenant auth. With no provider installed the server is single-tenant. See [Authentication](authentication-and-frontend.md#authentication) |
| `OAUTH_ISSUER_URL` | Public backend URL. Enables the [MCP endpoint](mcp-integration.md) |
| `ENABLE_EVALUATIONS` | Set `false` to disable the REST evaluate endpoint: it returns 403 and the frontend hides its button. Does not affect the CLI |

**Frontend service**: root directory `frontend`. It reads `API_URL` at runtime
(required), plus any `AUTH_PUBLIC_*` values its auth adapter needs.
None are compiled into the bundle, so one image serves any environment.

**Deploy order**: backend first, to get its URL. Set that as the frontend's
`API_URL`, deploy the frontend, then add the frontend's URL to the backend's
`ALLOWED_ORIGINS`.

`.env.example` documents every variable, including the ones that only matter
locally.
