import type { AuthProxyHandler, AuthProxyModule } from "../auth-adapter";

/**
 * Proxy delegate for the no-provider configuration: there is none, so the
 * platform's proxy is a pass-through.
 */
export const authProxyHandler: AuthProxyHandler | null = null;

const _conforms: AuthProxyModule = { authProxyHandler };
void _conforms;
