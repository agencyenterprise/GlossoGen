import type { AuthServerModule, AuthSession } from "../auth-adapter";

/**
 * Server-side session read for the no-provider configuration.
 *
 * Nobody is ever signed in, and no group is ever active, which is what puts the
 * platform in single-tenant mode: the backend resolves every request to the
 * synthetic `local` group regardless of what the URL says.
 */
export async function readSession(): Promise<AuthSession> {
  return { configured: false, userId: null, activeGroupSlug: null };
}

const _conforms: AuthServerModule = { readSession };
void _conforms;
