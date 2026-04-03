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
