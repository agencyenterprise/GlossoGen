"use client";

import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { humanize } from "./format";
import { roundSuccessShare } from "./run-row-details";

type RoundResultTally = components["schemas"]["RoundResultTally"];

/** Text colour for a success share: green from two thirds, amber from one third,
 *  red below. */
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
 * The rounds the scenario judged: one bar per team, one cell per judged round in
 * round order, green where that round succeeded and red where it failed, with
 * the fraction that succeeded beside it. Renders nothing for a scenario that
 * judges no rounds.
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
            <div className="flex flex-1 gap-px">
              {tally.rounds.map(round => (
                <span
                  key={round.round_number}
                  className={cn(
                    "h-1.5 flex-1 rounded-[1px]",
                    round.succeeded ? "bg-emerald-500" : "bg-red-400 dark:bg-red-500/80"
                  )}
                />
              ))}
            </div>
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
