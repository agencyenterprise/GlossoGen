"use client";

import type { ReactNode } from "react";
import { Tooltip } from "@/shared/components/ui/tooltip";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { humanize } from "./format";
import { type RoundMarker, roundSuccessShare } from "./run-row-details";

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
 * the fraction that succeeded beside it. Each marker is a tick between the last
 * round before its change and the next judged round, or at the bar's end when no
 * judged round follows it yet. Renders nothing for a scenario that judges no
 * rounds.
 */
export function RoundSuccessMeter({
  tallies,
  markers,
}: {
  tallies: RoundResultTally[];
  markers: RoundMarker[];
}) {
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
            <div className="flex flex-1 items-center gap-px">
              {interleaveMarkers({ tally, markers })}
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

/** The tally's round cells, with each marker placed before the first judged
 *  round past its change, and markers past every judged round at the end. */
function interleaveMarkers({
  tally,
  markers,
}: {
  tally: RoundResultTally;
  markers: RoundMarker[];
}): ReactNode[] {
  const items: ReactNode[] = [];
  let nextMarker = 0;
  for (const round of tally.rounds) {
    while (nextMarker < markers.length && markers[nextMarker]!.afterRound < round.round_number) {
      items.push(<MarkerTick key={`marker-${nextMarker}`} marker={markers[nextMarker]!} />);
      nextMarker += 1;
    }
    items.push(
      <span
        key={round.round_number}
        className={cn(
          "h-1.5 flex-1 rounded-[1px]",
          round.succeeded ? "bg-emerald-500" : "bg-red-400 dark:bg-red-500/80"
        )}
      />
    );
  }
  for (; nextMarker < markers.length; nextMarker += 1) {
    items.push(<MarkerTick key={`marker-${nextMarker}`} marker={markers[nextMarker]!} />);
  }
  return items;
}

function MarkerTick({ marker }: { marker: RoundMarker }) {
  return (
    <Tooltip label={marker.labels.join(" · ")} wrap={true}>
      <span className="flex h-3 w-1.5 justify-center">
        <span className="h-full w-0.5 rounded-full bg-foreground/70" />
      </span>
    </Tooltip>
  );
}
