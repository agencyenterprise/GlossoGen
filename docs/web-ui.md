# Web UI

A FastAPI backend and a Next.js frontend for browsing runs. The two are separate
processes; start each in its own terminal.

```bash
make dev            # terminal 1: FastAPI backend on port 8000 (reads ./runs/)
make dev-frontend   # terminal 2: Next.js dev server on port 3000
```

Open <http://localhost:3000> once both are up.

The run list shows scenario, timestamp, message count, status (including
in-progress runs), evaluation status, and lineage badges for every derived run
(fork, replace-agent, cross-run, resume-at-round). Opening a run gives the full
message timeline, agent reasoning, debug logs and evaluation results.

Simulations are launched from the [CLI](running-simulations.md) or via the MCP
[`start_run`](mcp-integration.md) tool, not from the run list.

Both targets assume this checkout. Installed as a dependency instead, one command
does both:

```bash
glossogen serve --runs-dir ./runs --port 8000 --ui-port 3000
```

`--ui-port` runs the published frontend image against the server it just
started, so a scenario or metric that ships in another package is browsed from
the environment that holds it. See
[Viewing your runs in the web UI](creating-a-scenario.md#viewing-your-runs-in-the-web-ui).

## Live streaming

Every `glossogen run` starts an embedded streaming server on an ephemeral port and
writes a `stream.json` discovery file into the run directory. When the web server
sees that file it proxies the simulation's SSE stream to connected browsers,
including token-by-token deltas, so text appears as agents generate it. When the
simulation ends, `stream.json` is deleted and the server falls back to tailing the
JSONL.

## Run labels

Labels are short tags on a run, for filtering and grouping. They live in
`labels.json` in the run directory as a JSON array of strings, and are editable
through `PUT /api/g/{group_slug}/runs/{scenario}/{run_dir_name}/labels`.

That PUT **replaces** the whole list rather than appending, and evaluation merges
its own entries into the same file. Apply labels before evaluating, or read the
existing list and write it back with your addition, or you will drop what
evaluation put there.

## Authentication

Two modes, switched by whether an identity provider is installed.

**Single-tenant mode**, the default for a clone and for `docker compose up`. Install
no provider. The identity middleware resolves every request to a synthetic `local`
group and `local-user`, and the frontend renders with no sign-in flow. With
`DATABASE_URL` also unset there is no database at all: the runs index comes from the
filesystem and OAuth state is held in memory. Setting `DATABASE_URL` keeps
single-tenant mode but stores the `local` group and the runs index in Postgres. It
performs no authentication, so do not expose it to a network.

**Multi-tenant mode**, for anything hosted. Multi-tenancy is in the platform:
`/g/[groupSlug]/` routing on the frontend, `/api/g/{group_slug}/...` on the backend,
the `groups` table, and the `Identity` attached to each request. What the platform
does not ship is a provider, so a deployment supplies one.

Each **organization in the identity provider** is a study **group**. Every run
belongs to exactly one group and is never shared across groups except through the
export/import flow. The active group is the URL slug: `/g/team-a/runs/...` on the
frontend hits `/api/g/team-a/runs/...` on the backend, and the request is accepted
only if the caller's session has `team-a` as its active group.

That split is deliberate. The credential proves *what the caller may do*; the URL
declares *what they are doing right now*. Nothing has to mutate shared session state
to change groups, so someone belonging to several can browse them in parallel tabs.

### The backend contract

A provider is a separate installed distribution declaring one entry point:

```toml
[project.entry-points."glossogen.identity_provider.v1"]
my_provider = "my_auth.identity_provider:MyIdentityProvider"
```

It implements `IdentityProvider`
([src/glossogen/server/identity/identity_provider.py](https://github.com/agencyenterprise/GlossoGen/blob/main/src/glossogen/server/identity/identity_provider.py)),
which has five members: a name for the logs, the path prefixes its own webhooks are
served on, the routers it contributes, where to send a browser that must choose a
group before an MCP token is minted, and `resolve_identity`.

`resolve_identity` is called only after the platform has extracted a bearer
credential and resolved the URL's slug to a `groups` row. So a provider answers one
question — does this credential grant access to this group, and as whom — and never
queries the `groups` table itself. It raises `IdentityRejected` with 401 for a
credential that does not verify and 403 for one that verifies but does not cover the
group.

### What the platform offers a provider

The contract above is one direction. A provider also needs things *from* the
platform, and those live in
[`identity/provider_services.py`](https://github.com/agencyenterprise/GlossoGen/blob/main/src/glossogen/server/identity/provider_services.py):

| Need | Call |
|---|---|
| Finish a deferred MCP authorization | `approve_parked_consent(request, request_id, group_id)` |
| Build the consent URL for `deferred_consent_url` | `frontend_base_url()` |
| Create or rename a group from an organization event | `glossogen.db.queries.upsert_group` |
| Delete one | `glossogen.db.queries.soft_delete_group_by_external_org_id` |

The soft delete clears the external id and keeps the row, so `runs.group_id` foreign
keys stay valid. Deleting the row would orphan runs.

Nothing in this repository calls those four, since their callers live in whichever
distribution supplies the provider. They carry vulture whitelist entries for that
reason, and `provider_services.py` exists so the surface is declared rather than
discovered by reading platform source.

Ambiguity is fatal rather than a warning. More than one declared provider, or one
declared under a group version the platform does not read, refuses to start. Warning
and continuing would boot a server that authenticates nothing while an operator
believes their provider is installed, which is indistinguishable from a deployment
that never configured one.

### The frontend contract

`frontend/src/features/auth/auth-adapter.ts` is the contract;
`frontend/src/features/auth/adapter/` is the implementation, and the copy in this
repository answers "no provider configured" to every slot. A deployment replaces that
directory. Four modules, one per runtime that imports them:

| Module | Runs in | Supplies |
|---|---|---|
| `adapter/proxy.ts` | the Next.js proxy | a delegate seeing every request, or `null` for pass-through |
| `adapter/server.ts` | Server Components | `readSession()`: the request's user and active group |
| `adapter/browser.ts` | the browser, no React | `getSessionToken()`: the bearer for API calls |
| `adapter/client.tsx` | client components | the provider wrapper, the group switcher, and the bodies of `/sign-in`, `/sign-up`, `/select-org`, `/mcp-consent` |

Those four routes stay in this repository as shells, because the App Router resolves
pages by file path. Each renders one adapter component and owns nothing else.
`src/proxy.ts` stays too, and keeps its `matcher` as a literal because Next.js reads
it statically and rejects a re-exported one.

An adapter's public configuration reaches the browser the same way `API_URL` does:
every `AUTH_PUBLIC_*` variable is read on the server, its prefix stripped, and
published as `RuntimeConfig.auth`. Those values are visible in page source. Secrets
stay server-side and never enter that object.

### Users in several groups

A provider whose service tracks one active organization per session can activate the
URL's group from its proxy delegate, for the current request, before the page renders
or the API client mints a token. That is what lets a user in several groups reach any
of them by URL without picking one first. If they are not a member, the backend sees
a session whose active group does not match the slug and answers 403.

## API type safety

Frontend API calls go through a typed client generated from the backend's OpenAPI
schema. Raw `fetch()` is refused by ESLint. After changing a response model,
regenerate:

```bash
make gen-api-types
```

CI fails if the committed types drift from the schema.

## Frontend plug-ins

A scenario can ship a `plugin.tsx` for a bespoke round-detail panel, tool-metadata
renderer, timeline marker or live-judge wiring. Plug-ins are compiled into the
bundle, so they live in this repository even when the scenario itself does not. A
scenario with no plug-in renders through the default one: preset-driven controls
built from the knobs JSON Schema the scenario already publishes, which is enough
for most scenarios. See
[Creating a scenario](creating-a-scenario.md#12-optional-add-a-frontend-plug-in).
