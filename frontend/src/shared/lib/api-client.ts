import createClient from "openapi-fetch";
import type { paths } from "@/types/api.gen";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = createClient<paths>({
  baseUrl: API_URL,
});

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
 * When Clerk is loaded in the browser, fetch a fresh session token via the
 * global `window.Clerk` accessor. Returns ``null`` in local mode (no
 * Clerk) or before Clerk has finished initializing — the backend's
 * identity middleware treats those requests as the synthetic local
 * identity.
 */
async function getClerkSessionToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  const clerk = (
    window as unknown as { Clerk?: { session?: { getToken: () => Promise<string | null> } } }
  ).Clerk;
  const session = clerk?.session;
  if (!session) return null;
  try {
    return await session.getToken();
  } catch {
    return null;
  }
}

function substituteGroupSlug(url: string): string {
  if (_activeGroupSlug === null) return url;
  const encoded = encodeURIComponent(_activeGroupSlug);
  return url.replace("{group_slug}", encoded).replace("%7Bgroup_slug%7D", encoded);
}

export function buildApiUrlWithToken({
  path,
  searchParams,
}: {
  path: string;
  searchParams: URLSearchParams;
}): string {
  const substituted = substituteGroupSlug(path);
  const query = searchParams.toString();
  if (query.length > 0) {
    return `${API_URL}${substituted}?${query}`;
  }
  return `${API_URL}${substituted}`;
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
  const query = searchParams.toString();
  const url = query.length > 0 ? `${API_URL}${substituted}?${query}` : `${API_URL}${substituted}`;
  const headers: Record<string, string> = {};
  const token = await getClerkSessionToken();
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
    const substituted = substituteGroupSlug(request.url);
    let outgoing = request;
    if (substituted !== request.url) {
      outgoing = new Request(substituted, request);
    }
    const token = await getClerkSessionToken();
    if (token) {
      outgoing.headers.set("Authorization", `Bearer ${token}`);
    }
    return outgoing;
  },
});
