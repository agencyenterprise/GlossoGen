"use client";

import { useState } from "react";
import { AlertTriangle, ChevronDown, ChevronRight } from "lucide-react";

interface RunCycleFailureDisplayProps {
  errorType: string;
  message: string;
  cycle: number;
}

/** Renders an AgentRunCycleFailed entry as a compact, expandable error pill.
 *  Shows the exception class name and cycle number by default; click to
 *  reveal the full exception message. */
export function RunCycleFailureDisplay({ errorType, message, cycle }: RunCycleFailureDisplayProps) {
  const [expanded, setExpanded] = useState(false);
  const ChevronIcon = expanded ? ChevronDown : ChevronRight;

  return (
    <div className="rounded border border-red-300/70 bg-red-50/50 px-2 py-1 text-[11px] dark:border-red-800/50 dark:bg-red-950/20">
      <button
        type="button"
        onClick={() => setExpanded(prev => !prev)}
        className="flex w-full items-center gap-1.5 text-left"
      >
        <AlertTriangle className="h-3 w-3 shrink-0 text-red-600 dark:text-red-400" />
        <span className="font-medium text-red-700 dark:text-red-300">{errorType}</span>
        <span className="text-red-600/70 dark:text-red-400/70">retry {cycle}</span>
        <ChevronIcon className="ml-auto h-3 w-3 shrink-0 text-red-600/60 dark:text-red-400/60" />
      </button>
      {expanded ? (
        <pre className="mt-1 whitespace-pre-wrap break-words text-red-800/80 dark:text-red-300/80">
          {message}
        </pre>
      ) : null}
    </div>
  );
}
