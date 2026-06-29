import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";

/**
 * Fetch public server feature flags from ``GET /api/server-config``.
 *
 * The flags are server-wide and rarely change during a session, so the
 * query never goes stale and is shared across components via its query key.
 */
export function useServerConfig() {
  return useQuery({
    queryKey: ["server-config"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/server-config");
      if (error) {
        throw new Error("Failed to fetch server config");
      }
      return data;
    },
    staleTime: Infinity,
  });
}
