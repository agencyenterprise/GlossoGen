"use client";

import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";

type DebugLogEntry = components["schemas"]["DebugLogEntry"];

const LEVEL_STYLES: Record<string, string> = {
  DEBUG: "text-muted-foreground",
  INFO: "text-foreground",
  WARNING: "text-yellow-600 dark:text-yellow-400",
  ERROR: "text-red-600 dark:text-red-400",
};

function formatLogTime(isoTimestamp: string): string {
  const date = new Date(isoTimestamp);
  return date.toLocaleTimeString("en-US", { hour12: false, fractionalSecondDigits: 1 });
}

function shortenLoggerName(name: string): string {
  const parts = name.split(".");
  return parts[parts.length - 1] ?? name;
}

interface LogPanelProps {
  logs: DebugLogEntry[];
}

export function LogPanel({ logs }: LogPanelProps) {
  if (logs.length === 0) {
    return (
      <div className="flex items-center justify-center py-10 text-sm text-muted-foreground">
        No debug logs available for this run.
      </div>
    );
  }

  return (
    <div className="flex flex-col overflow-hidden">
      <div className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-2.5">
        <span className="text-[13px] font-medium">Debug logs</span>
        <span className="text-xs text-muted-foreground">{logs.length} entries</span>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        <div className="font-mono text-[11px] leading-relaxed">
          {logs.map((entry, i) => (
            <div key={i} className="flex gap-2 px-2 py-px hover:bg-muted/50">
              <span className="shrink-0 text-muted-foreground">
                {formatLogTime(entry.timestamp)}
              </span>
              <span className={cn("w-12 shrink-0 font-medium", LEVEL_STYLES[entry.level])}>
                {entry.level}
              </span>
              <span className="shrink-0 text-muted-foreground/70">
                {shortenLoggerName(entry.logger_name)}
              </span>
              <span className={cn(LEVEL_STYLES[entry.level])}>{entry.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
