"use client";

import { useCallback, useRef, useState } from "react";
import { createPortal } from "react-dom";

interface TooltipProps {
  label: string;
  children: React.ReactElement<React.HTMLAttributes<HTMLElement>>;
}

/**
 * Portal-based tooltip that renders above all scroll containers and overlays.
 *
 * Matches the styling of the CSS-only tooltips used elsewhere in the app
 * but works correctly near scrollbar edges by rendering into document.body.
 */
export function Tooltip({ label, children }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const triggerRef = useRef<HTMLElement | null>(null);
  const [position, setPosition] = useState({ top: 0, left: 0 });

  const show = useCallback(() => {
    if (triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      setPosition({
        top: rect.bottom + 4,
        left: rect.left + rect.width / 2,
      });
    }
    setVisible(true);
  }, []);

  const hide = useCallback(() => {
    setVisible(false);
  }, []);

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
      {visible
        ? createPortal(
            <span
              style={{ top: position.top, left: position.left }}
              className="pointer-events-none fixed z-[9999] -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg"
            >
              {label}
            </span>,
            document.body
          )
        : null}
    </>
  );
}
