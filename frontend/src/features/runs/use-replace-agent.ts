"use client";

import { useMutation } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import { splitRunId } from "@/shared/lib/run-id";

interface ReplaceAgentArgs {
  roundStart: number;
  replacedAgentId: string;
  model: string;
  provider: string;
  channelsWithVisibleHistory: string[];
  knobs: Record<string, unknown> | null;
}

export function useReplaceAgent(runId: string) {
  return useMutation({
    mutationFn: async (args: ReplaceAgentArgs) => {
      const { data, error } = await api.POST("/api/runs/{scenario}/{run_dir_name}/replace-agent", {
        params: { path: splitRunId(runId) },
        body: {
          round_start: args.roundStart,
          replaced_agent_id: args.replacedAgentId,
          model: args.model,
          provider: args.provider,
          knobs: args.knobs,
          channels_with_visible_history: args.channelsWithVisibleHistory,
        },
      });
      if (error) {
        const detail = (error as { detail?: unknown }).detail;
        const message =
          typeof detail === "string"
            ? detail
            : detail !== undefined
              ? JSON.stringify(detail)
              : "Failed to launch replace-agent run";
        throw new Error(message);
      }
      return data;
    },
    onSuccess: data => {
      window.location.href = `/runs/${data.new_run_id}`;
    },
  });
}
