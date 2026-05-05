"use client";

import { useMutation } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import { splitRunId } from "@/shared/lib/run-id";

interface CrossRunReplaceAgentArgs {
  sourceBRunId: string;
  roundStart: number;
  sourceBRoundEnd: number | null;
  roundsAfterSwap: number;
  replacedAgentId: string;
  model: string | null;
  provider: string | null;
  channelsWithVisibleHistory: string[];
  knobs: Record<string, unknown> | null;
}

export function useCrossRunReplaceAgent(runId: string) {
  return useMutation({
    mutationFn: async (args: CrossRunReplaceAgentArgs) => {
      const { data, error } = await api.POST(
        "/api/runs/{scenario}/{run_dir_name}/cross-run-replace-agent",
        {
          params: { path: splitRunId(runId) },
          body: {
            source_b_run_id: args.sourceBRunId,
            round_start: args.roundStart,
            source_b_round_end: args.sourceBRoundEnd,
            rounds_after_swap: args.roundsAfterSwap,
            replaced_agent_id: args.replacedAgentId,
            model: args.model,
            provider: args.provider,
            knobs: args.knobs,
            channels_with_visible_history: args.channelsWithVisibleHistory,
          },
        }
      );
      if (error) {
        const detail = (error as { detail?: unknown }).detail;
        const message =
          typeof detail === "string"
            ? detail
            : detail !== undefined
              ? JSON.stringify(detail)
              : "Failed to launch cross-run replace-agent run";
        throw new Error(message);
      }
      return data;
    },
    onSuccess: data => {
      window.location.href = `/runs/${data.new_run_id}`;
    },
  });
}
