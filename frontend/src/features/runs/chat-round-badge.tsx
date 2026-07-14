"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Hash } from "lucide-react";
import { Tooltip } from "@/shared/components/ui/tooltip";
import { cn } from "@/shared/lib/cn";

/**
 * The floating "Round N" badge over the chat, plus its jump-to-round dropdown.
 *
 * Owns the dropdown's open state, anchor ref, and outside-click / Escape
 * dismissal. ``onOpenTimeline`` opens the round timeline modal for the current
 * round; ``onScrollToRound`` scrolls the chat to a chosen round (the scroll
 * itself stays in ``ChatPane``, which holds the round-marker refs).
 */
export function ChatRoundBadge({
  currentVisibleRound,
  sortedRoundNumbers,
  onOpenTimeline,
  onScrollToRound,
}: {
  currentVisibleRound: number;
  sortedRoundNumbers: number[];
  onOpenTimeline: (roundNumber: number) => void;
  onScrollToRound: (roundNumber: number) => void;
}) {
  const [showRoundJumper, setShowRoundJumper] = useState(false);
  const roundJumperRef = useRef<HTMLDivElement | null>(null);

  // Close the round jumper on outside click or Escape.
  useEffect(() => {
    if (!showRoundJumper) return;
    function handleMouseDown(e: MouseEvent) {
      if (roundJumperRef.current && !roundJumperRef.current.contains(e.target as Node)) {
        setShowRoundJumper(false);
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setShowRoundJumper(false);
    }
    document.addEventListener("mousedown", handleMouseDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleMouseDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [showRoundJumper]);

  return (
    <div className="absolute left-1/2 top-12 z-30 flex -translate-x-1/2 items-center gap-1.5">
      <button
        type="button"
        aria-label={`Open round ${currentVisibleRound} timeline`}
        onClick={() => onOpenTimeline(currentVisibleRound)}
        className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-border bg-background/90 px-2.5 py-1 text-[11px] font-medium text-muted-foreground shadow-sm backdrop-blur transition-colors hover:border-foreground/30 hover:bg-background hover:text-foreground"
      >
        <Hash className="h-3 w-3" />
        Round {currentVisibleRound}
      </button>
      {sortedRoundNumbers.length > 1 ? (
        <div ref={roundJumperRef} className="relative">
          <Tooltip label="Jump to round">
            <button
              type="button"
              aria-haspopup="listbox"
              aria-expanded={showRoundJumper}
              aria-label="Jump to round"
              onClick={() => setShowRoundJumper(v => !v)}
              className="inline-flex cursor-pointer items-center justify-center rounded-full border border-border bg-background/90 p-1 text-muted-foreground shadow-sm backdrop-blur transition-colors hover:border-foreground/30 hover:bg-background hover:text-foreground"
            >
              <ChevronDown className="h-3 w-3" />
            </button>
          </Tooltip>
          {showRoundJumper ? (
            <div
              role="listbox"
              aria-label="Rounds"
              className="absolute right-0 top-full z-40 mt-1 w-32 overflow-hidden rounded-md border border-border bg-background shadow-lg"
            >
              <div className="max-h-64 overflow-y-auto py-1">
                {sortedRoundNumbers.map(n => (
                  <button
                    key={n}
                    type="button"
                    role="option"
                    aria-selected={n === currentVisibleRound}
                    onClick={() => {
                      onScrollToRound(n);
                      setShowRoundJumper(false);
                    }}
                    className={cn(
                      "block w-full px-3 py-1 text-left text-[11px] transition-colors hover:bg-muted",
                      n === currentVisibleRound
                        ? "font-medium text-foreground"
                        : "text-muted-foreground"
                    )}
                  >
                    Round {n}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
