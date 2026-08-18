import createClient from "openapi-fetch";
import { getApiUrl } from "@/shared/config/runtime-config";
import { getSessionToken } from "@/features/auth/adapter/browser";
import type { paths } from "@/types/api.gen";

/**
 * Placeholder origin handed to openapi-fetch at module load.
 *
 * `createClient` captures `baseUrl` when it is constructed, which is import
 * time — too early to know the runtime API URL. Requests are therefore built
 * against this sentinel and rewritten to the real origin in the `onRequest`
 * middleware below, which already reconstructs every request. The sentinel is
 * never dialled; a request escaping with this origin means the rewrite was
 * skipped, and it fails loudly rather than silently hitting the wrong host.
 */
const SENTINEL_ORIGIN = "http://runtime-config.invalid";

export const api = createClient<paths>({
  baseUrl: SENTINEL_ORIGIN,
});

/** Swap the sentinel origin for the runtime API URL. */
function resolveApiOrigin(url: string): string {
  if (!url.startsWith(SENTINEL_ORIGIN)) {
    return url;
  }
  return `${getApiUrl()}${url.slice(SENTINEL_ORIGIN.length)}`;
}

/**
 * Module-level mirror of the currently active group slug.
 *
 * Updated by ``<GroupProvider>`` (which the ``/g/[groupSlug]`` layout
 * renders) so the openapi-fetch onRequest middleware can substitute
 * ``{group_slug}`` placeholders in URLs without every call site having to
 * pass ``params.path.group_slug``. ``null`` outside any group context (the
 * sign-in pages, etc.) — requests with unsubstituted placeholders will be
 * rewritten to literally include the placeholder text and the backend
 * will 404 them, which is fine because such requests shouldn't happen.
 */
let _activeGroupSlug: string | null = null;

export function setActiveGroupSlug(slug: string | null): void {
  _activeGroupSlug = slug;
}

/**
 * ``Authorization`` header for raw ``fetch`` calls that cannot go through
 * openapi-fetch, such as multipart uploads. Returns a bearer header when an auth
 * adapter supplies a token, and an empty object in single-tenant mode, where the
 * backend supplies the synthetic identity.
 */
export async function authHeaders(): Promise<Record<string, string>> {
  const token = await getSessionToken();
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

function substituteGroupSlug(url: string): string {
  if (_activeGroupSlug === null) return url;
  const encoded = encodeURIComponent(_activeGroupSlug);
  return url.replace("{group_slug}", encoded).replace("%7Bgroup_slug%7D", encoded);
}

/**
 * Reject API URLs that still contain the literal `{group_slug}` placeholder.
 *
 * Happens during the brief window between page navigation and the
 * ``<GroupProvider>`` ``useEffect`` running that primes ``_activeGroupSlug``.
 * Letting such a request go out produces a backend 401 (or worse, a
 * literal ``/api/g/{group_slug}/...`` row in the log). Throwing instead
 * lets TanStack Query treat it as a transient error and retry once
 * the slug is set.
 */
function assertGroupSlugSubstituted(url: string): void {
  if (url.includes("{group_slug}") || url.includes("%7Bgroup_slug%7D")) {
    throw new Error("Active group slug not yet initialized; the request will retry");
  }
}

/**
 * Build a fully-qualified URL for an SSE (`EventSource`) connection.
 *
 * `EventSource` cannot set an `Authorization` header, so the session token, when
 * there is one, is appended as a `?token=` query parameter, which the backend
 * identity middleware accepts as a bearer fallback. Returns the URL with no token
 * in single-tenant mode. Async because obtaining a fresh token is async.
 */
export async function buildEventStreamUrl({
  path,
  searchParams,
}: {
  path: string;
  searchParams: URLSearchParams;
}): Promise<string> {
  const substituted = substituteGroupSlug(path);
  assertGroupSlugSubstituted(substituted);
  const token = await getSessionToken();
  if (token) {
    searchParams.set("token", token);
  }
  const query = searchParams.toString();
  if (query.length > 0) {
    return `${getApiUrl()}${substituted}?${query}`;
  }
  return `${getApiUrl()}${substituted}`;
}

function extractFilename(disposition: string | null, fallback: string): string {
  if (!disposition) return fallback;
  const quoted = disposition.match(/filename="([^"]+)"/);
  if (quoted && quoted[1]) return quoted[1];
  const bare = disposition.match(/filename=([^;]+)/);
  if (bare && bare[1]) return bare[1].trim();
  return fallback;
}

export async function downloadAuthenticatedFile({
  path,
  searchParams,
  fallbackFilename,
}: {
  path: string;
  searchParams: URLSearchParams;
  fallbackFilename: string;
}): Promise<void> {
  const substituted = substituteGroupSlug(path);
  assertGroupSlugSubstituted(substituted);
  const query = searchParams.toString();
  const base = getApiUrl();
  const url = query.length > 0 ? `${base}${substituted}?${query}` : `${base}${substituted}`;
  const headers: Record<string, string> = {};
  const token = await getSessionToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  // eslint-disable-next-line no-restricted-globals -- binary download, openapi-fetch returns typed JSON only
  const resp = await fetch(url, { headers });
  if (!resp.ok) {
    throw new Error(`Download failed: ${resp.status} ${resp.statusText}`);
  }
  const blob = await resp.blob();
  const filename = extractFilename(resp.headers.get("Content-Disposition"), fallbackFilename);
  const blobUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = blobUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(blobUrl);
}

api.use({
  async onRequest({ request }) {
    const substituted = resolveApiOrigin(substituteGroupSlug(request.url));
    assertGroupSlugSubstituted(substituted);
    const token = await getSessionToken();

    const headers = new Headers(request.headers);
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    // Rebuild the request explicitly rather than via ``new Request(url,
    // request)``: that form transfers the body stream and drops it for
    // bodied requests in some browsers, so PUT/POST payloads arrive empty and
    // the backend 422s. Capturing the body bytes here preserves it reliably.
    const hasBody = request.method !== "GET" && request.method !== "HEAD";
    const body = hasBody ? await request.arrayBuffer() : undefined;
    return new Request(substituted, {
      method: request.method,
      headers,
      body,
      signal: request.signal,
      credentials: request.credentials,
    });
  },
});
