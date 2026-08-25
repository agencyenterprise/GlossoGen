# Authentication and the frontend

How a deployment extends the platform around the web UI: installing an
identity provider for multi-tenant hosting, replacing the frontend's auth
adapter, and shipping scenario UI plug-ins.

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

The credential says what the caller may do. The URL says what they are doing
right now. Nothing has to mutate shared session state to change groups, so someone
belonging to several groups can browse them in parallel tabs.

### The backend contract

A provider is a separate installed distribution declaring one entry point:

```toml
[project.entry-points."glossogen.identity_provider.v1"]
my_provider = "my_auth.identity_provider:MyIdentityProvider"
```

It implements `IdentityProvider`
([src/glossogen/server/identity/identity_provider.py](https://github.com/agencyenterprise/GlossoGen/blob/main/src/glossogen/server/identity/identity_provider.py)),
whose members are: a name for the logs, the path prefixes its own webhooks are
served on, the routers it contributes, where to send a browser that must choose a
group before an MCP token is minted, and `resolve_identity`.

`resolve_identity` is called only after the platform has extracted a bearer
credential and resolved the URL's slug to a `groups` row. So a provider answers one
question, whether this credential grants access to this group and as whom, and
never queries the `groups` table itself. It raises `IdentityRejected` with 401 for a
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
declared under an entry-point version the platform does not read, refuses to start. Warning
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
scenario without one renders through the platform's generic timeline and round
views, which is enough for most scenarios. See
[Creating a scenario](creating-a-scenario.md#frontend-plug-in).
