import type { AuthBrowserModule } from "../auth-adapter";

/**
 * Token read for the no-provider configuration.
 *
 * Null means outgoing API calls carry no `Authorization` header, and the backend
 * supplies the synthetic single-tenant identity instead.
 *
 * Deliberately carries no `"use client"` directive and imports no React, because
 * `api-client.ts` imports this and is itself imported from modules with no
 * directive of their own.
 */
export async function getSessionToken(): Promise<string | null> {
  return null;
}

const _conforms: AuthBrowserModule = { getSessionToken };
void _conforms;
