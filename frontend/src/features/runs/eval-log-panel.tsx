"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/shared/lib/cn";
import { api } from "@/shared/lib/api-client";
import { splitRunId } from "@/shared/lib/run-id";

/** Threshold in pixels for considering the user "at the bottom" of the scroll area. */
const SCROLL_BOTTOM_THRESHOLD = 80;

interface EvalLogPanelProps {
  runId: string;
  evaluationInProgress: boolean;
}

export function EvalLogPanel({ runId, evaluationInProgress }: EvalLogPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const prevScrollHeightRef = useRef(0);

  const { data } = useQuery({
    queryKey: ["eval-logs", runId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/runs/{scenario}/{run_dir_name}/eval-logs", {
        params: { path: splitRunId(runId) },
      });
      if (error) throw new Error("Failed to fetch eval logs");
      return data;
    },
    refetchInterval: evaluationInProgress ? 3_000 : false,
  });

  const lines = data?.lines ?? [];

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

  // Auto-scroll when new lines arrive via MutationObserver
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

  if (lines.length === 0) {
    return (
      <div className="flex items-center justify-center py-10 text-sm text-muted-foreground">
        No evaluation logs available for this run.
      </div>
    );
  }

  return (
    <div className="flex flex-col overflow-hidden">
      <div className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-2.5">
        <span className="text-[13px] font-medium">Evaluation logs</span>
        <span className="text-xs text-muted-foreground">{lines.length} lines</span>
        {evaluationInProgress ? (
          <span className="rounded-full bg-yellow-500/10 px-2 py-0.5 text-[10px] font-medium text-yellow-600 dark:text-yellow-400">
            running
          </span>
        ) : null}
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-2" onScroll={handleScroll}>
        <div className="font-mono text-[11px] leading-relaxed">
          {lines.map(line => (
            <div
              key={line.line_number}
              className={cn(
                "px-2 py-px hover:bg-muted/50",
                isErrorLine(line.text) ? "text-red-600 dark:text-red-400" : "text-foreground"
              )}
            >
              {line.text}
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

function isErrorLine(text: string): boolean {
  return (
    text.includes("Traceback") ||
    text.includes("Error") ||
    text.includes("ERROR") ||
    text.includes("CRITICAL")
  );
}
