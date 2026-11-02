"use client";

import { CheckCircle2 } from "lucide-react";
import type { components } from "@/types/api.gen";
import { humanize } from "./format";
import { HoverPopover } from "./hover-popover";

type EvaluationScore = components["schemas"]["EvaluationScore"];

/** The Evaluated badge, whose hover popover lists the scores the run listing
 *  already returned for the run. `scores` is null when the run's report exists
 *  but could not be read. */
export function EvaluationBadge({ scores }: { scores: EvaluationScore[] | null }) {
  return (
    <HoverPopover
      triggerClassName="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
      trigger={
        <>
          <CheckCircle2 className="h-2.5 w-2.5" />
          Evaluated
        </>
      }
      layoutKey={scores}
    >
      {scores === null ? (
        <span className="text-muted-foreground">Evaluation report could not be read.</span>
      ) : scores.length === 0 ? (
        <span className="text-muted-foreground">No measurements recorded.</span>
      ) : (
        <div className="space-y-0.5">
          {scores.map((m, index) => (
            <div
              key={`${m.metric_name}::${index}`}
              title={m.summary}
              className="flex items-baseline justify-between gap-4"
            >
              <span>{humanize(m.metric_name)}</span>
              <span className="font-mono text-muted-foreground">
                {m.score.toFixed(2)}
                <span className="ml-1 text-[10px] opacity-60">{m.score_unit}</span>
              </span>
            </div>
          ))}
        </div>
      )}
    </HoverPopover>
  );
}
