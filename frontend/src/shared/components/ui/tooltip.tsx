"use client";

import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const VIEWPORT_MARGIN = 8;

interface TooltipProps {
  label: string;
  /** Wrapping, width-capped body for sentence-length labels; nowrap for short ones. */
  wrap: boolean;
  children: React.ReactElement<React.HTMLAttributes<HTMLElement>>;
}

/**
 * Portal-based tooltip that renders above all scroll containers and overlays.
 *
 * Matches the styling of the CSS-only tooltips used elsewhere in the app
 * but works correctly near scrollbar edges by rendering into document.body.
 * Positioned from its real rendered width and clamped to the viewport, so a
 * trigger near a screen edge shows the whole text instead of spilling off it.
 */
export function Tooltip({ label, wrap, children }: TooltipProps) {
  const [anchor, setAnchor] = useState<{ top: number; center: number } | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const tipRef = useRef<HTMLSpanElement | null>(null);

  const show = useCallback(() => {
    if (triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      setAnchor({ top: rect.bottom + 4, center: rect.left + rect.width / 2 });
    }
  }, []);

  const hide = useCallback(() => {
    setAnchor(null);
  }, []);

  // Runs before paint, so the clamped position is the only one ever shown.
  useLayoutEffect(() => {
    const tip = tipRef.current;
    if (anchor === null || tip === null) {
      return;
    }
    const half = tip.offsetWidth / 2;
    const lowestCenter = VIEWPORT_MARGIN + half;
    const highestCenter = window.innerWidth - VIEWPORT_MARGIN - half;
    const center = Math.min(
      Math.max(anchor.center, lowestCenter),
      Math.max(lowestCenter, highestCenter)
    );
    tip.style.left = `${center - half}px`;
  }, [anchor, label]);

  return (
    <>
      <span
        ref={triggerRef as React.RefObject<HTMLSpanElement>}
        onMouseEnter={show}
        onMouseLeave={hide}
        className="inline-flex"
      >
        {children}
      </span>
      {anchor !== null
        ? createPortal(
            <span
              ref={tipRef}
              style={{ top: anchor.top, left: anchor.center }}
              className={`pointer-events-none fixed z-[9999] rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg ${
                wrap ? "block w-max max-w-64" : "whitespace-nowrap"
              }`}
            >
              {label}
            </span>,
            document.body
          )
        : null}
    </>
  );
}
