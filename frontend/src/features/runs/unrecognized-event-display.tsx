"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, FileQuestion } from "lucide-react";
import { formatTime } from "./format";

interface UnrecognizedEventDisplayProps {
  eventType: string;
  timestamp: string;
  payload: Record<string, unknown> | null;
}

/** Renders a logged event the server does not parse for the run's scenario
 *  (its scenario is not loaded here, or no longer declares the type) as a
 *  muted pill naming its type; click to reveal the logged line as JSON. */
export function UnrecognizedEventDisplay({
  eventType,
  timestamp,
  payload,
}: UnrecognizedEventDisplayProps) {
  const [expanded, setExpanded] = useState(false);
  const ChevronIcon = expanded ? ChevronDown : ChevronRight;

  return (
    <div className="rounded border border-dashed border-border px-2 py-1 text-[11px] text-muted-foreground">
      <button
        type="button"
        onClick={() => setExpanded(prev => !prev)}
        className="flex w-full items-center gap-1.5 text-left"
        title="An event of a type this server does not parse for this run's scenario"
      >
        <FileQuestion className="h-3 w-3 shrink-0" />
        <span className="font-mono">{eventType}</span>
        <span className="text-muted-foreground/70">unrecognized event</span>
        <span className="text-[10px] text-muted-foreground/60">{formatTime(timestamp)}</span>
        <ChevronIcon className="ml-auto h-3 w-3 shrink-0" />
      </button>
      {expanded ? (
        <pre className="mt-1 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded bg-muted/40 p-2 font-mono text-[10px]">
          {JSON.stringify(payload, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}
