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

Two modes, switched by whether `CLERK_SECRET_KEY` is set on the backend.

**Local mode**, the default for dev clones. Leave `CLERK_SECRET_KEY` unset on the
backend and `CLERK_PUBLISHABLE_KEY` unset on the frontend. The identity middleware
short-circuits every request to a synthetic `local` group and `local-user`, and the
frontend renders with no sign-in flow. With `DATABASE_URL` also unset there is no
database at all: the runs index comes from the filesystem and OAuth state is held
in memory. Setting `DATABASE_URL` keeps local mode but stores the `local` group and
the runs index in Postgres.

**Clerk mode**, for anything hosted. Set the Clerk variables on both sides, plus
`CLERK_WEBHOOK_SECRET` so the backend keeps its `groups` table in sync with org
create / update / delete events. The frontend mounts `<ClerkProvider>` and
redirects unauthenticated traffic to `/sign-in`. API requests carry the Clerk
session token as a Bearer header.

Each Clerk **organization** is a study **group**. Every run belongs to exactly one
group and is never shared across groups except through the export/import flow. The
active group is the URL slug: `/g/team-a/runs/...` on the frontend hits
`/api/g/team-a/runs/...` on the backend, and the request is accepted only if the
user's Clerk session has `team-a` as its active org.

### Users in several organizations

`frontend/src/proxy.ts` wires Clerk's
`organizationSyncOptions.organizationPatterns` to `["/g/:slug", "/g/:slug/(.*)"]`.
Clerk's middleware reads the slug from the URL and activates that org on the
session for the current request, before the page renders or the API client mints a
token. So a user in several orgs can reach any of them by URL without touching the
org switcher first.

If the user is not a member of the URL's org, Clerk leaves the previously active
org in place, the backend sees `claims.org_slug != url_slug`, and the request gets
a 403.

**One tab at a time, in the cookie.** Clerk's session cookie is a singleton per
browser, so only one tab's active org is reflected in it. Each tab still activates
its own org server-side on navigation, so page loads and Server-Component fetches
are correct, and the API client mints a token per request rather than reading the
cookie, so foreground requests match the tab's URL. A background fetch that never
passes through the focused tab could race, though there are none today.

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
