"use client";

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { type AnchorBox, type PopoverPosition, placePopover } from "./popover-placement";

const HOVER_OPEN_DELAY_MS = 250;
const HOVER_CLOSE_DELAY_MS = 80;

/**
 * A badge whose hover opens a popover with richer content than a tooltip: rows,
 * scores, a scrolling list. The popover is portalled to the body, placed by
 * :func:`placePopover`, and stays open while the pointer is over it, so its
 * content can be scrolled.
 *
 * ``layoutKey`` re-places an open popover when the content it shows changes.
 * Clicks on the badge and the popover do not reach the row underneath.
 */
export function HoverPopover({
  trigger,
  triggerClassName,
  layoutKey,
  children,
}: {
  trigger: ReactNode;
  triggerClassName: string;
  layoutKey: unknown;
  children: ReactNode;
}) {
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
  // before the browser paints if the content changes while it is open. The
  // height is the content's full height, read through scrollHeight, so a cap
  // from an earlier placement does not hide how tall the list is.
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
  }, [popover, layoutKey]);

  return (
    <>
      <span
        ref={anchorRef}
        className={triggerClassName}
        onMouseEnter={openSoon}
        onMouseLeave={closeSoon}
        onClick={e => e.stopPropagation()}
      >
        {trigger}
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
                {children}
              </div>
            </div>,
            document.body
          )
        : null}
    </>
  );
}
