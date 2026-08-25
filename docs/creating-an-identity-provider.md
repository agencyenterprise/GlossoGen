# Creating an identity provider

A hosted, multi-tenant deployment authenticates through an identity provider: a
separate installed distribution that answers whether a credential grants access
to a group, and as whom. The platform ships none, and single-tenant mode needs
none. The two modes are described under
[Deployment](deployment.md#authentication).

A provider spans both services. On the backend it is an entry point the server
loads. On the frontend it is an auth adapter compiled into the UI image.

## The backend contract

A provider declares one entry point:

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

Ambiguity refuses to boot: more than one declared provider, or one declared
under an entry-point version the platform does not read, stops the server,
because running unauthenticated while an operator believes a provider is
installed is worse than not starting.

## What the platform offers a provider

The contract above is one direction. A provider also needs things *from* the
platform, and those live in
[`identity/provider_services.py`](https://github.com/agencyenterprise/GlossoGen/blob/main/src/glossogen/server/identity/provider_services.py):

| Need | Call |
|---|---|
| Finish a deferred MCP authorization | `approve_parked_consent(request, request_id, group_id)` |
| Build the consent URL for `deferred_consent_url` | `frontend_base_url()` |
| Create or rename a group from an organization event | `glossogen.db.queries.upsert_group` |
| Delete one | `glossogen.db.queries.soft_delete_group_by_external_org_id` |

The soft delete clears the external id and keeps the row, so `runs.group_id`
foreign keys stay valid. Deleting the row would orphan runs.

## The frontend contract

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

Those four routes stay in this repository as shells, because the App Router
resolves pages by file path. Each renders one adapter component and owns nothing
else.

An adapter's public configuration reaches the browser the same way `API_URL` does:
every `AUTH_PUBLIC_*` variable is read on the server, its prefix stripped, and
published as `RuntimeConfig.auth`. Those values are visible in page source. Secrets
stay server-side and never enter that object.

## Users in several groups

A provider whose service tracks one active organization per session can activate the
URL's group from its proxy delegate, for the current request, before the page renders
or the API client mints a token. That is what lets a user in several groups reach any
of them by URL without picking one first. If they are not a member, the backend sees
a session whose active group does not match the slug and answers 403.
