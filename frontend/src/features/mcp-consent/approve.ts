import { getApiUrl } from "@/shared/config/runtime-config";
import { getSessionToken } from "@/features/auth/adapter/browser";

/**
 * Approve a parked MCP authorization request and return the OAuth client's
 * callback URL.
 *
 * The endpoint and its payload are the platform's own API, so this stays
 * platform-side; only the bearer comes from the auth adapter. The backend resolves
 * that token to a group and mints the authorization code bound to it.
 */
export async function approveMcpConsent({ requestId }: { requestId: string }): Promise<string> {
  const token = await getSessionToken();
  if (token === null) {
    throw new Error("No session token available to approve with");
  }
  const apiUrl = getApiUrl();
  // eslint-disable-next-line no-restricted-globals -- /mcp/consent/approve is provider-contributed, so it is not in the typed OpenAPI surface
  const response = await fetch(`${apiUrl}/mcp/consent/approve`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ request_id: requestId }),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Backend rejected approval (${response.status}): ${detail}`);
  }
  const data = (await response.json()) as { redirect_url: string };
  return data.redirect_url;
}
