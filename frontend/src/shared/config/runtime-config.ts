/**
 * Runtime configuration, resolved per deployment rather than per build.
 *
 * Next.js replaces every `process.env.NEXT_PUBLIC_*` reference with a literal
 * string when the bundle is compiled, so anything read that way is fixed at
 * build time. That makes a compiled image environment-specific: a single
 * frontend image cannot be promoted from staging to production, because the
 * backend URL and the auth adapter's key are already baked into its JavaScript.
 *
 * Instead the server reads unprefixed variables — which are genuine runtime
 * reads on the server — and hands them to the browser through a small inline
 * script (see `runtime-config-script.tsx`). Client code reads them back
 * through the accessors below.
 *
 * Adding a value here means: extend `RuntimeConfig`, read it in
 * `readServerRuntimeConfig`, and expose an accessor. Nothing else changes.
 */

export interface RuntimeConfig {
  /** Absolute base URL of the backend API, no trailing slash. */
  apiUrl: string;
  /**
   * Public configuration for the auth adapter: every `AUTH_PUBLIC_*` variable
   * with the prefix stripped. Empty means single-tenant mode.
   *
   * A map rather than named fields because the platform cannot know what values
   * a given provider needs. Browser-visible, so only values safe in page source
   * belong here; an adapter reads its secrets from `process.env` on the server
   * and they never enter this object.
   */
  auth: Record<string, string>;
}

/** Prefix marking an environment variable as the auth adapter's, and public. */
const AUTH_PUBLIC_PREFIX = "AUTH_PUBLIC_";

/** Name of the browser global carrying the server-injected config. */
export const RUNTIME_CONFIG_GLOBAL = "__GLOSSOGEN_RUNTIME_CONFIG__";

declare global {
  interface Window {
    __GLOSSOGEN_RUNTIME_CONFIG__?: RuntimeConfig;
  }
}

function readEnv(name: string): string | null {
  const value = process.env[name];
  if (value === undefined) {
    return null;
  }
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return null;
  }
  return trimmed;
}

/**
 * Read the runtime config on the server, from unprefixed environment
 * variables. Safe to call from Server Components, route handlers, and the
 * proxy — never from client code, where `process.env` is not populated.
 *
 * `API_URL` is required: defaulting it would let a misconfigured deployment
 * serve a frontend that silently calls the wrong host, which is exactly the
 * failure the build-time approach produced.
 */
export function readServerRuntimeConfig(): RuntimeConfig {
  const apiUrl = readEnv("API_URL");
  if (apiUrl === null) {
    throw new Error(
      "API_URL is not set. Point it at the backend, e.g. http://localhost:8000 " +
        "for local development."
    );
  }
  return {
    apiUrl: apiUrl.replace(/\/+$/, ""),
    auth: readAuthConfig(),
  };
}

/** Collect every `AUTH_PUBLIC_*` variable, prefix stripped. */
function readAuthConfig(): Record<string, string> {
  const collected: Record<string, string> = {};
  for (const [name, raw] of Object.entries(process.env)) {
    if (!name.startsWith(AUTH_PUBLIC_PREFIX)) continue;
    const value = raw?.trim();
    if (value === undefined || value.length === 0) continue;
    collected[name.slice(AUTH_PUBLIC_PREFIX.length)] = value;
  }
  return collected;
}

/**
 * Read the runtime config from whichever side is calling.
 *
 * On the server this reads the environment directly. In the browser it reads
 * the global injected before hydration. Resolved lazily on each call rather
 * than cached at module scope, so import order cannot race the injection.
 */
export function getRuntimeConfig(): RuntimeConfig {
  if (typeof window === "undefined") {
    return readServerRuntimeConfig();
  }
  const injected = window[RUNTIME_CONFIG_GLOBAL];
  if (injected === undefined) {
    throw new Error(
      `${RUNTIME_CONFIG_GLOBAL} is missing. The root layout must render ` +
        "<RuntimeConfigScript /> before any component reads runtime config."
    );
  }
  return injected;
}

/** Absolute base URL of the backend API, with no trailing slash. */
export function getApiUrl(): string {
  return getRuntimeConfig().apiUrl;
}

/** One of the adapter's public values, or null when it is absent. */
export function getAuthConfigValue(name: string): string | null {
  const value = getRuntimeConfig().auth[name];
  if (value === undefined || value.length === 0) {
    return null;
  }
  return value;
}
