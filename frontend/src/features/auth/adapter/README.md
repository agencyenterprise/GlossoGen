# The auth adapter

This directory is the only place the frontend knows how a visitor proves who they
are. The contract it satisfies is [`../auth-adapter.ts`](../auth-adapter.ts), which
the platform owns.

A deployment that needs different authentication replaces this whole directory.
**Replace it, never merge into it:** a stale file left behind by a merge still
compiles, and `noUnusedLocals` will not catch it.

```
rm -rf src/features/auth/adapter
cp -R <your-adapter> src/features/auth/adapter
```

## Four modules, one per runtime

The split follows React's module graph, not taste. One module exporting all four
of these cannot be imported from all four places.

| Module       | Runs in                                      | Supplies                                                                                                   |
| ------------ | -------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `proxy.ts`   | the Next.js proxy, edge runtime              | `authProxyHandler`, or `null` for pass-through                                                             |
| `server.ts`  | Server Components                            | `readSession()`: the request's user and active group                                                       |
| `browser.ts` | the browser, no React, **no `"use client"`** | `getSessionToken()`: the bearer for API calls                                                              |
| `client.tsx` | client components                            | the provider wrapper, the top bar, and the bodies of `/sign-in`, `/sign-up`, `/select-org`, `/mcp-consent` |

`browser.ts` carries no directive on purpose. `api-client.ts` imports it, and that
is imported from modules with no directive of their own, so anything React-flavoured
here breaks the build.

Each module ends with an assignment to its contract type, so renaming a slot in the
contract fails `tsc` here rather than at a call site.

## Configuration

Public values reach the browser through the platform's request-time config: every
`AUTH_PUBLIC_*` environment variable is collected on the server, the prefix
stripped, and published as `RuntimeConfig.auth`. Read one with
`getAuthConfigValue("PUBLISHABLE_KEY")`.

Those values are visible in page source. Secrets stay on the server, read from
`process.env` inside `proxy.ts` or `server.ts`, and must never enter
`RuntimeConfig`.

This is what keeps one compiled image usable in any environment, so an adapter must
not introduce a `NEXT_PUBLIC_*` read or a Docker build argument.

## The routes stay in the platform

`/sign-in`, `/sign-up`, `/select-org` and `/mcp-consent` are shells under
`src/app/`, because the App Router resolves pages by file path and they cannot live
out of tree. Each renders one component from `client.tsx` and owns nothing else.
`src/proxy.ts` stays too, and keeps its `matcher` as a literal because Next.js reads
it statically and rejects a re-exported one.

## What this copy does

Nothing. Every slot answers "no provider configured", which is single-tenant mode:
the proxy is a pass-through, `readSession()` reports nobody signed in,
`getSessionToken()` returns null, and the backend resolves every request to the
synthetic `local` group.

Because those answers are real rather than absent, the platform's call sites need no
branch on whether an adapter is installed, and the four auth routes render a short
explanation rather than a blank page.
