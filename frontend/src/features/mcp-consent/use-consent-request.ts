import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import { apiError } from "@/shared/lib/api-error";

/**
 * Fetch the client name and callback URL of a parked MCP consent request from
 * ``GET /mcp/consent-request/{request_id}``.
 *
 * A request is single-use and expires, so a failed fetch is not retried: the
 * page reports it and the user starts the sign-in again from their client.
 */
export function useConsentRequest(requestId: string) {
  return useQuery({
    queryKey: ["mcp-consent-request", requestId],
    queryFn: async () => {
      const { data, error } = await api.GET("/mcp/consent-request/{request_id}", {
        params: { path: { request_id: requestId } },
      });
      if (error) {
        throw apiError(error, "Failed to load the authorization request");
      }
      return data;
    },
    retry: false,
    staleTime: Infinity,
  });
}
