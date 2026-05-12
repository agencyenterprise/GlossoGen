"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Loader2 } from "lucide-react";
import { api } from "@/shared/lib/api-client";
import { splitRunId } from "@/shared/lib/run-id";
import { humanize } from "./format";

const HOVER_OPEN_DELAY_MS = 250;
const HOVER_CLOSE_DELAY_MS = 80;

export function EvaluationBadge({ runId }: { runId: string }) {
  const [popover, setPopover] = useState<{ left: number; top: number } | null>(null);
  const openTimerRef = useRef<number | null>(null);
  const closeTimerRef = useRef<number | null>(null);
  const anchorRef = useRef<HTMLSpanElement | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["run-evaluation", runId],
    enabled: popover !== null,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/runs/{scenario}/{run_dir_name}/evaluation", {
        params: { path: splitRunId(runId) },
      });
      if (error) {
        throw new Error("Failed to fetch evaluation");
      }
      return data;
    },
    staleTime: 60_000,
  });

  function clearOpenTimer() {
    if (openTimerRef.current !== null) {
      window.clearTimeout(openTimerRef.current);
      openTimerRef.current = null;
    }
  }

  function clearCloseTimer() {
    if (closeTimerRef.current !== null) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }

  function openSoon() {
    clearCloseTimer();
    if (popover !== null || openTimerRef.current !== null) {
      return;
    }
    openTimerRef.current = window.setTimeout(() => {
      openTimerRef.current = null;
      const rect = anchorRef.current?.getBoundingClientRect();
      if (!rect) {
        return;
      }
      setPopover({ left: rect.left, top: rect.bottom + 4 });
    }, HOVER_OPEN_DELAY_MS);
  }

  function closeSoon() {
    clearOpenTimer();
    clearCloseTimer();
    closeTimerRef.current = window.setTimeout(() => {
      setPopover(null);
      closeTimerRef.current = null;
    }, HOVER_CLOSE_DELAY_MS);
  }

  useEffect(() => {
    return () => {
      clearOpenTimer();
      clearCloseTimer();
    };
  }, []);

  useEffect(() => {
    if (popover === null) {
      return undefined;
    }
    const dismiss = () => setPopover(null);
    window.addEventListener("scroll", dismiss, true);
    window.addEventListener("resize", dismiss);
    return () => {
      window.removeEventListener("scroll", dismiss, true);
      window.removeEventListener("resize", dismiss);
    };
  }, [popover]);

  return (
    <>
      <span
        ref={anchorRef}
        className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
        onMouseEnter={openSoon}
        onMouseLeave={closeSoon}
        onClick={e => e.stopPropagation()}
      >
        <CheckCircle2 className="h-2.5 w-2.5" />
        Evaluated
      </span>
      {popover !== null ? (
        <div className="pointer-events-none fixed inset-0 z-50">
          <div
            className="pointer-events-auto absolute w-max max-w-md rounded-md border border-border bg-background px-3 py-2 text-xs shadow-lg"
            style={{
              left: `${Math.max(8, popover.left)}px`,
              top: `${popover.top}px`,
            }}
            onMouseEnter={clearCloseTimer}
            onMouseLeave={closeSoon}
            onClick={e => e.stopPropagation()}
          >
            {isLoading ? (
              <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                Loading…
              </span>
            ) : data ? (
              data.measurements.length === 0 ? (
                <span className="text-muted-foreground">No measurements recorded.</span>
              ) : (
                <div className="space-y-0.5">
                  {data.measurements.map((m, index) => (
                    <div
                      key={`${m.metric_name}::${index}`}
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
              )
            ) : (
              <span className="text-muted-foreground">Evaluation report not available.</span>
            )}
          </div>
        </div>
      ) : null}
    </>
  );
}
