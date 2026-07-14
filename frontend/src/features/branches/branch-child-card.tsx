"use client";

import { GitFork } from "lucide-react";
import Link from "next/link";
import type { components } from "@/types/api.gen";
import { useGroupPath } from "@/features/auth/group-context";
import { formatTime } from "../runs/format";

type RunStatus = components["schemas"]["RunStatus"];
type DerivedRunReference = components["schemas"]["DerivedRunReference"];

const STATUS_LABELS: Record<RunStatus, string> = {
  scenario_complete: "Completed",
  in_progress: "In Progress",
  starting: "Starting",
  error: "Error",
  killed: "Killed",
};

const DERIVATION_LABELS: Record<DerivedRunReference["derivation_type"], string> = {
  replace_agent: "Replace",
  resume_at_round: "Resume",
  cross_run_replace_agent: "Cross-run",
};

/** The model a child ran under, when the derivation swapped or imported one. */
function childModel(child: DerivedRunReference): string | null {
  if (child.replacement_model !== null) {
    return child.replacement_model;
  }
  if (child.imported_model !== null) {
    return child.imported_model;
  }
  return null;
}

interface BranchChildCardProps {
  runs: DerivedRunReference[];
}

/** Renders the runs that branch from the trunk at a given round boundary. */
export function BranchChildCard({ runs }: BranchChildCardProps) {
  const groupPath = useGroupPath();
  return (
    <div className="rounded-md border border-violet-200 bg-violet-50/60 dark:border-violet-800/50 dark:bg-violet-950/30">
      {runs.map(child => {
        const model = childModel(child);
        return (
          <Link
            key={child.run_id}
            href={groupPath(`/runs/${child.run_id}`)}
            className="flex flex-wrap items-center gap-2 px-3 py-1.5 text-xs transition-colors first:rounded-t-md last:rounded-b-md hover:bg-violet-100/80 dark:hover:bg-violet-900/40"
          >
            <GitFork className="h-3 w-3 shrink-0 text-violet-600 dark:text-violet-400" />
            <span className="rounded-full bg-violet-200/70 px-1.5 py-0.5 text-[10px] font-medium text-violet-800 dark:bg-violet-800/40 dark:text-violet-200">
              {DERIVATION_LABELS[child.derivation_type]}
            </span>
            <span className="font-mono text-violet-700 dark:text-violet-300">
              {child.run_id.split("/").pop()}
            </span>
            {model !== null ? <span className="text-muted-foreground">{model}</span> : null}
            <span
              className={`text-[10px] font-medium ${
                child.status === "in_progress"
                  ? "text-green-600 dark:text-green-400"
                  : child.status === "error"
                    ? "text-red-600 dark:text-red-400"
                    : "text-muted-foreground"
              }`}
            >
              {STATUS_LABELS[child.status] ?? child.status}
            </span>
            <span className="ml-auto text-muted-foreground">{formatTime(child.created_at)}</span>
          </Link>
        );
      })}
    </div>
  );
}
