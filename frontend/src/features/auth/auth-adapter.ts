/**
 * Auth adapter contract.
 *
 * The platform renders routing, tenancy and the group-scoped API surface, but it
 * does not know how a visitor proves who they are. It reads identity through the
 * four modules under `adapter/`, and a deployment that needs authentication
 * replaces that directory with an implementation satisfying the types here.
 *
 * The split into proxy / server / browser / client follows React's module graph
 * rather than taste. `readSession` runs in a Server Component and needs a
 * server-only import; `AuthProvider` is a client component; `getSessionToken`
 * runs in the browser with no React at all, so `api-client.ts` stays importable
 * from either side; and the proxy delegate runs in the edge runtime. One module
 * exporting all four cannot be imported from all four places.
 *
 * Each adapter module ends with an assignment to the matching type below, so a
 * slot renamed here fails `tsc` in the adapter rather than at a call site.
 */

import type { ComponentType, ReactNode } from "react";
import type { NextFetchEvent, NextRequest } from "next/server";

/** Delegate for the Next.js proxy convention file. `null` means pass-through. */
export type AuthProxyHandler = (
  request: NextRequest,
  event: NextFetchEvent
) => Response | null | undefined | Promise<Response | null | undefined>;

/** Who the current server request belongs to. */
export interface AuthSession {
  /** The provider's stable user id, or null when nobody is signed in. */
  userId: string | null;
  /** The group slug active for this request, or null when none is. */
  activeGroupSlug: string | null;
}

/** The group an MCP consent approval will be bound to. */
export interface ConsentIdentity {
  groupName: string;
  groupSlug: string;
}

/** `adapter/proxy.ts` — edge runtime. */
export interface AuthProxyModule {
  authProxyHandler: AuthProxyHandler | null;
}

/** `adapter/server.ts` — Server Components only. */
export interface AuthServerModule {
  readSession: () => Promise<AuthSession>;
}

/** `adapter/browser.ts` — the browser, no React, no directive. */
export interface AuthBrowserModule {
  /** Bearer token for outgoing API calls, or null when unauthenticated. */
  getSessionToken: () => Promise<string | null>;
}

/** `adapter/client.tsx` — client components. */
export interface AuthClientModule {
  /**
   * Wraps the whole tree from the root layout. Renders children unchanged when
   * no provider is configured.
   */
  AuthProvider: ComponentType<{ children: ReactNode }>;
  /**
   * Group switcher and account menu, mounted inside every group-scoped route.
   * Renders nothing when no provider is configured.
   */
  AuthTopBar: ComponentType;
  /** Body of `/sign-in`. */
  SignInView: ComponentType;
  /** Body of `/sign-up`. */
  SignUpView: ComponentType;
  /**
   * Body of `/select-org`. `hrefForGroup` is the platform's destination for a
   * chosen or newly created group.
   */
  GroupPickerView: ComponentType<{ hrefForGroup: (slug: string) => string }>;
  /**
   * Signs the visitor in if needed, settles which group they are authorizing,
   * then renders `children(identity)`. With no provider configured the backend
   * auto-approves and never redirects a browser to `/mcp-consent`, so this
   * reports that rather than rendering a flow.
   */
  ConsentGate: ComponentType<{
    requestId: string;
    children: (identity: ConsentIdentity) => ReactNode;
  }>;
}
