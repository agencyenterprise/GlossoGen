"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
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
  const h = String(date.getHours()).padStart(2, "0");
  const m = String(date.getMinutes()).padStart(2, "0");
  const s = String(date.getSeconds()).padStart(2, "0");
  const ms = String(Math.floor(date.getMilliseconds() / 100));
  return `${h}:${m}:${s}.${ms}`;
}

function shortenLoggerName(name: string): string {
  const parts = name.split(".");
  return parts[parts.length - 1] ?? name;
}

/** Threshold in pixels for considering the user "at the bottom" of the scroll area. */
const SCROLL_BOTTOM_THRESHOLD = 80;

interface LogPanelProps {
  logs: DebugLogEntry[];
}

export function LogPanel({ logs }: LogPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const prevScrollHeightRef = useRef(0);

  // Scroll to bottom on initial render
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight;
        prevScrollHeightRef.current = el.scrollHeight;
      });
    }
  }, []);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_BOTTOM_THRESHOLD;
    isAtBottomRef.current = atBottom;
    setIsAtBottom(atBottom);
    prevScrollHeightRef.current = el.scrollHeight;
  }, []);

  // Auto-scroll when new logs arrive via MutationObserver
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return undefined;

    const observer = new MutationObserver(() => {
      if (!isAtBottomRef.current) return;
      if (el.scrollHeight <= prevScrollHeightRef.current) return;
      prevScrollHeightRef.current = el.scrollHeight;
      el.scrollTop = el.scrollHeight;
    });

    observer.observe(el, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, []);

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
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-2" onScroll={handleScroll}>
        <div className="font-mono text-[11px] leading-relaxed">
          {logs.map((entry, i) => (
            <div key={i} className="flex gap-3 px-2 py-px hover:bg-muted/50">
              <span className="w-[10ch] shrink-0 text-muted-foreground">
                {formatLogTime(entry.timestamp)}
              </span>
              <span className={cn("w-[5ch] shrink-0 font-medium", LEVEL_STYLES[entry.level])}>
                {entry.level}
              </span>
              <span className="w-[14ch] shrink-0 truncate text-muted-foreground/70">
                {shortenLoggerName(entry.logger_name)}
              </span>
              <span className={cn("min-w-0", LEVEL_STYLES[entry.level])}>{entry.message}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Auto-scroll status bar */}
      <div className="flex shrink-0 items-center justify-center border-t border-border px-4 py-1.5">
        {isAtBottom ? (
          <span className="text-[11px] text-muted-foreground">Auto-scroll enabled</span>
        ) : (
          <button
            className="flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-0.5 text-[11px] font-medium text-muted-foreground shadow-sm transition-colors hover:bg-muted hover:text-foreground"
            onClick={scrollToBottom}
          >
            <ChevronDown className="h-3 w-3" />
            Scroll to bottom
          </button>
        )}
      </div>
    </div>
  );
}
