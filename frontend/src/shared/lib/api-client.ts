import createClient from "openapi-fetch";
import type { paths } from "@/types/api.gen";
import { AUTH_STORAGE_KEY } from "@/features/auth/auth-gate";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = createClient<paths>({
  baseUrl: API_URL,
});

export function buildApiUrlWithToken({
  path,
  searchParams,
}: {
  path: string;
  searchParams: URLSearchParams;
}): string {
  const params = new URLSearchParams(searchParams);
  if (typeof window !== "undefined") {
    const password = localStorage.getItem(AUTH_STORAGE_KEY);
    if (password) {
      params.set("token", password);
    }
  }
  const query = params.toString();
  if (query.length > 0) {
    return `${API_URL}${path}?${query}`;
  }
  return `${API_URL}${path}`;
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
  const query = searchParams.toString();
  const url = query.length > 0 ? `${API_URL}${path}?${query}` : `${API_URL}${path}`;
  const headers: Record<string, string> = {};
  if (typeof window !== "undefined") {
    const password = localStorage.getItem(AUTH_STORAGE_KEY);
    if (password) {
      headers["Authorization"] = `Bearer ${password}`;
    }
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
    if (typeof window !== "undefined") {
      const password = localStorage.getItem(AUTH_STORAGE_KEY);
      if (password) {
        request.headers.set("Authorization", `Bearer ${password}`);
      }
    }
    return request;
  },
  async onResponse({ response }) {
    if (response.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem(AUTH_STORAGE_KEY);
      window.location.reload();
    }
    return response;
  },
});
