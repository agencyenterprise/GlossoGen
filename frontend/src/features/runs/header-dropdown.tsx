"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/shared/lib/cn";

/**
 * The trigger button and popover shell shared by the run header's dropdowns
 * ("Run info", "Knobs"). Owns open state plus outside-click and Escape
 * dismissal. ``children`` is a render prop receiving a ``close`` callback, so a
 * row inside the panel can dismiss it before opening a modal.
 *
 * ``align`` is the panel edge that lines up with the trigger. A trigger on the
 * right of its container needs "right" so the panel opens inward; one on the
 * left needs "left", or a panel wider than the trigger runs off the viewport.
 */
export function HeaderDropdown({
  label,
  icon,
  badge,
  align,
  panelClassName,
  children,
}: {
  label: string;
  icon: ReactNode;
  badge: string | null;
  align: "left" | "right";
  panelClassName: string;
  children: (close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function handleMouseDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handleMouseDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleMouseDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <span ref={containerRef} className="relative">
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(value => !value)}
        className={cn(
          "inline-flex items-center gap-1 rounded px-1 py-0.5 text-[12px] font-medium transition-colors hover:bg-muted hover:text-foreground",
          open ? "bg-muted text-foreground" : "text-muted-foreground"
        )}
      >
        {icon}
        {label}
        {badge !== null ? (
          <span className="rounded-full bg-muted px-1.5 text-[10px] leading-4 text-muted-foreground">
            {badge}
          </span>
        ) : null}
        <ChevronDown className={cn("h-3 w-3 transition-transform", open ? "rotate-180" : "")} />
      </button>
      {open ? (
        <div
          className={cn(
            "absolute top-full z-50 mt-1 rounded-md border border-border bg-background text-xs shadow-lg",
            align === "right" ? "right-0" : "left-0",
            panelClassName
          )}
        >
          {children(() => setOpen(false))}
        </div>
      ) : null}
    </span>
  );
}
