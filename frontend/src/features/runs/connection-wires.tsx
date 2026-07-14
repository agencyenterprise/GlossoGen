"use client";

import { useLayoutEffect, useState, type RefObject } from "react";

/** A read_notifications call pill paired with its response chip, connected by a wire. */
export interface NotificationPair {
  callMessageId: string;
  resultMessageId: string;
  callId: string;
}

interface WireShape {
  callId: string;
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  color: string;
}

/** Deterministic hue from a call_id so each wire gets a stable unique color. */
function hueFromCallId(callId: string): number {
  let h = 0;
  for (let i = 0; i < callId.length; i += 1) {
    h = (h * 31 + callId.charCodeAt(i)) >>> 0;
  }
  return h % 360;
}

/** Renders curved SVG wires inside the scrollable content connecting each
 *  read_notifications call pill to its response chip. Each wire is a cubic
 *  bezier that bulges out to the left of the column. Wires re-measure on
 *  layout changes via ResizeObserver + MutationObserver so they stay aligned
 *  as entries expand or new messages arrive. */
export function ConnectionWires({
  pairs,
  messageRefs,
  containerRef,
  hoveredCallId,
}: {
  pairs: NotificationPair[];
  messageRefs: RefObject<Map<string, HTMLDivElement>>;
  containerRef: RefObject<HTMLDivElement | null>;
  hoveredCallId: string | null;
}) {
  const [wires, setWires] = useState<WireShape[]>([]);

  useLayoutEffect(() => {
    let rafId: number | null = null;
    let attemptsLeft = 60;
    let ro: ResizeObserver | null = null;
    let mo: MutationObserver | null = null;

    function schedule() {
      if (rafId !== null) return;
      rafId = requestAnimationFrame(recompute);
    }

    function recompute() {
      rafId = null;
      const containerEl = containerRef.current;
      if (containerEl === null) {
        // Container not yet mounted — retry next frame.
        if (attemptsLeft > 0) {
          attemptsLeft -= 1;
          rafId = requestAnimationFrame(recompute);
        }
        return;
      }
      // Attach observers once, as soon as the container exists. The
      // ResizeObserver catches layout shifts (entry expansion, window resize).
      // The MutationObserver catches late-mounting entries on huge runs
      // streamed in after our initial rAF retry budget is exhausted.
      if (ro === null) {
        ro = new ResizeObserver(schedule);
        ro.observe(containerEl);
      }
      if (mo === null) {
        mo = new MutationObserver(schedule);
        mo.observe(containerEl, { childList: true, subtree: true });
      }
      const containerRect = containerEl.getBoundingClientRect();
      const next: WireShape[] = [];
      for (const pair of pairs) {
        const callEl = messageRefs.current.get(pair.callMessageId);
        const resultEl = messageRefs.current.get(pair.resultMessageId);
        if (callEl === undefined || resultEl === undefined) continue;
        const callRect = callEl.getBoundingClientRect();
        const resultRect = resultEl.getBoundingClientRect();
        const callMid = callRect.top + callRect.height / 2 - containerRect.top;
        const resultMid = resultRect.top + resultRect.height / 2 - containerRect.top;
        const callX = callRect.left - containerRect.left;
        const resultX = resultRect.left - containerRect.left;
        next.push({
          callId: pair.callId,
          startX: callX,
          startY: callMid,
          endX: resultX,
          endY: resultMid,
          color: `hsl(${hueFromCallId(pair.callId)}, 72%, 55%)`,
        });
      }
      setWires(prev => {
        if (prev.length !== next.length) return next;
        for (let i = 0; i < prev.length; i += 1) {
          const a = prev[i];
          const b = next[i];
          if (a === undefined || b === undefined) return next;
          if (
            a.callId !== b.callId ||
            Math.abs(a.startY - b.startY) > 0.5 ||
            Math.abs(a.endY - b.endY) > 0.5 ||
            Math.abs(a.startX - b.startX) > 0.5 ||
            Math.abs(a.endX - b.endX) > 0.5
          ) {
            return next;
          }
        }
        return prev;
      });
      // Refs on large runs can attach across many paints. Keep retrying on
      // animation frames until every pair is measured, then stop. Further
      // updates come from the ResizeObserver for layout shifts.
      if (next.length < pairs.length && attemptsLeft > 0) {
        attemptsLeft -= 1;
        rafId = requestAnimationFrame(recompute);
      }
    }

    recompute();
    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      if (ro !== null) ro.disconnect();
      if (mo !== null) mo.disconnect();
    };
  }, [pairs, messageRefs, containerRef]);

  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full"
      style={{ overflow: "visible" }}
      aria-hidden="true"
    >
      {wires.map(w => {
        const dy = Math.abs(w.endY - w.startY);
        // Bulge leftward; proportional to vertical distance, capped.
        const bulge = Math.min(80, Math.max(24, dy * 0.25));
        const c1x = w.startX - bulge;
        const c2x = w.endX - bulge;
        const d = `M ${w.startX} ${w.startY} C ${c1x} ${w.startY}, ${c2x} ${w.endY}, ${w.endX} ${w.endY}`;
        const isHovered = hoveredCallId === w.callId;
        return (
          <g key={w.callId}>
            <path
              d={d}
              stroke={w.color}
              strokeWidth={isHovered ? 2.5 : 1.5}
              strokeOpacity={isHovered ? 0.95 : 0.55}
              strokeLinecap="round"
              fill="none"
            />
            <circle cx={w.startX} cy={w.startY} r={isHovered ? 3.5 : 2.5} fill={w.color} />
            <circle cx={w.endX} cy={w.endY} r={isHovered ? 3.5 : 2.5} fill={w.color} />
          </g>
        );
      })}
    </svg>
  );
}
