"use client";

import { useMutation } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import { splitRunId } from "@/shared/lib/run-id";
import { useGroupPath } from "@/features/auth/group-context";

interface ResumeAtRoundArgs {
  roundStart: number;
  roundsAfterResume: number | null;
  knobs: Record<string, unknown> | null;
}

export function useResumeAtRound(runId: string) {
  const groupPath = useGroupPath();
  return useMutation({
    mutationFn: async (args: ResumeAtRoundArgs) => {
      const { data, error } = await api.POST(
        "/api/g/{group_slug}/runs/{scenario}/{run_dir_name}/resume-at-round",
        {
          params: { path: splitRunId(runId) },
          body: {
            round_start: args.roundStart,
            rounds_after_resume: args.roundsAfterResume,
            knobs: args.knobs,
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
              : "Failed to launch resume-at-round run";
        throw new Error(message);
      }
      return data;
    },
    onSuccess: data => {
      window.location.href = groupPath(`/runs/${data.new_run_id}`);
    },
  });
}
