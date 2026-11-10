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

/**
 * Unreachable here: the platform asks for a sign-in redirect only when
 * `readSession()` reports a configured provider, and this one never does. It throws
 * rather than redirecting, so a call that does arrive shows up as an error.
 */
export async function redirectToSignIn(): Promise<never> {
  throw new Error("redirectToSignIn was called, but no auth provider is configured");
}

const _conforms: AuthServerModule = { readSession, redirectToSignIn };
void _conforms;
