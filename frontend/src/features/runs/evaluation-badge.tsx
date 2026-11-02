"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { CheckCircle2 } from "lucide-react";
import type { components } from "@/types/api.gen";
import { humanize } from "./format";
import { type AnchorBox, type PopoverPosition, placePopover } from "./popover-placement";

type EvaluationScore = components["schemas"]["EvaluationScore"];

const HOVER_OPEN_DELAY_MS = 250;
const HOVER_CLOSE_DELAY_MS = 80;

/** The Evaluated badge, whose hover popover lists the scores the run listing
 *  already returned for the run. `scores` is null when the run's report exists
 *  but could not be read. */
export function EvaluationBadge({ scores }: { scores: EvaluationScore[] | null }) {
  const [popover, setPopover] = useState<AnchorBox | null>(null);
  const [position, setPosition] = useState<PopoverPosition | null>(null);
  const openTimerRef = useRef<number | null>(null);
  const closeTimerRef = useRef<number | null>(null);
  const anchorRef = useRef<HTMLSpanElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);

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
      setPopover({ left: rect.left, top: rect.top, bottom: rect.bottom });
    }, HOVER_OPEN_DELAY_MS);
  }

  function closeSoon() {
    clearOpenTimer();
    clearCloseTimer();
    closeTimerRef.current = window.setTimeout(() => {
      setPopover(null);
      setPosition(null);
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
    const dismiss = () => {
      setPopover(null);
      setPosition(null);
    };
    // Scrolling the popover's own list leaves it where it was placed.
    const dismissUnlessInsidePopover = (event: Event) => {
      if (event.target instanceof Node && popoverRef.current?.contains(event.target)) {
        return;
      }
      dismiss();
    };
    window.addEventListener("scroll", dismissUnlessInsidePopover, true);
    window.addEventListener("resize", dismiss);
    return () => {
      window.removeEventListener("scroll", dismissUnlessInsidePopover, true);
      window.removeEventListener("resize", dismiss);
    };
  }, [popover]);

  // Placed once rendered, since its size depends on what it shows, and again
  // before the browser paints if the scores change while it is open. The height
  // is the content's full height, read through scrollHeight, so a cap from an
  // earlier placement does not hide how tall the list is.
  useLayoutEffect(() => {
    const element = popoverRef.current;
    if (popover === null || element === null) {
      return;
    }
    const borderHeight = element.offsetHeight - element.clientHeight;
    setPosition(
      placePopover({
        anchor: popover,
        width: element.getBoundingClientRect().width,
        height: element.scrollHeight + borderHeight,
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
      })
    );
  }, [popover, scores]);

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
      {popover !== null && typeof document !== "undefined"
        ? createPortal(
            <div className="pointer-events-none fixed inset-0 z-50">
              <div
                ref={popoverRef}
                className="pointer-events-auto absolute w-max max-w-md overflow-y-auto overscroll-contain rounded-md border border-border bg-background px-3 py-2 text-xs shadow-lg"
                style={{
                  left: `${position?.left ?? popover.left}px`,
                  top: `${position?.top ?? popover.bottom}px`,
                  maxHeight: position === null ? undefined : `${position.maxHeight}px`,
                  visibility: position === null ? "hidden" : "visible",
                }}
                onMouseEnter={clearCloseTimer}
                onMouseLeave={closeSoon}
                onClick={e => e.stopPropagation()}
              >
                {scores === null ? (
                  <span className="text-muted-foreground">
                    Evaluation report could not be read.
                  </span>
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
              </div>
            </div>,
            document.body
          )
        : null}
    </>
  );
}
