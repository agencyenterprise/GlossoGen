"use client";

import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { humanize } from "./format";
import { roundSuccessShare } from "./run-row-details";

type RoundResultTally = components["schemas"]["RoundResultTally"];

/** Above this many judged rounds the bar is one fill instead of a cell per round,
 *  since the cells get too thin to tell apart. */
const MAX_SEGMENTED_ROUNDS = 30;

/** Fill colour for a success share: green from two thirds, amber from one third,
 *  red below. */
function shareFillClass(share: number): string {
  if (share >= 2 / 3) {
    return "bg-emerald-500";
  }
  if (share >= 1 / 3) {
    return "bg-amber-500";
  }
  return "bg-red-500";
}

/** Text colour matching :func:`shareFillClass`. */
function shareTextClass(share: number): string {
  if (share >= 2 / 3) {
    return "text-emerald-700 dark:text-emerald-400";
  }
  if (share >= 1 / 3) {
    return "text-amber-700 dark:text-amber-400";
  }
  return "text-red-700 dark:text-red-400";
}

/**
 * The rounds the scenario judged successful: one bar per team, one cell per
 * judged round, filled for each success, with the fraction beside it. Renders
 * nothing for a scenario that judges no rounds.
 */
export function RoundSuccessMeter({ tallies }: { tallies: RoundResultTally[] }) {
  if (tallies.length === 0) {
    return null;
  }
  return (
    <div className="flex w-full flex-col gap-0.5">
      {tallies.map(tally => {
        const share = roundSuccessShare([tally]) ?? 0;
        return (
          <div key={tally.team_id ?? "all"} className="flex items-center gap-1.5">
            {tally.team_id !== null ? (
              <span className="w-12 truncate text-[10px] text-muted-foreground">
                {humanize(tally.team_id)}
              </span>
            ) : null}
            {tally.judged <= MAX_SEGMENTED_ROUNDS ? (
              <div className="flex flex-1 gap-px">
                {Array.from({ length: tally.judged }, (_, index) => (
                  <span
                    key={index}
                    className={cn(
                      "h-1.5 flex-1 rounded-[1px]",
                      index < tally.succeeded ? shareFillClass(share) : "bg-muted"
                    )}
                  />
                ))}
              </div>
            ) : (
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                <div
                  className={cn("h-full", shareFillClass(share))}
                  style={{ width: `${share * 100}%` }}
                />
              </div>
            )}
            <span
              className={cn(
                "w-10 text-right font-mono text-[10px] tabular-nums",
                shareTextClass(share)
              )}
            >
              {tally.succeeded}/{tally.judged}
            </span>
          </div>
        );
      })}
    </div>
  );
}
