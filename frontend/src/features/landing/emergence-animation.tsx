"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Pause, Play, Wrench } from "lucide-react";
import { cn } from "@/shared/lib/cn";

/**
 * Looping story of how a compact protocol emerges, played as a single live,
 * append-only transcript that scrolls — like the real run viewer. Round 1: the
 * agents are verbose on the budgeted comm link and fail. In the off-the-clock
 * postmortem they agree on short codes. Round 2: tiny messages, patient
 * stabilizes. Content only ever grows within a cycle (then the "session"
 * restarts). Messages are from a real run (veyru/1780427522).
 */

type Who = "FO" | "SE";
type Event =
  | { kind: "divider"; label: string; tone: "round" | "postmortem" }
  | { kind: "inject"; text: string }
  | { kind: "message"; who: Who; channel: "link" | "postmortem"; text: string; cost?: string }
  | { kind: "tool"; name: string; arg: string }
  | { kind: "outcome"; ok: boolean; text: string };

const STEP_MS = 1400;

const EVENTS: Event[] = [
  { kind: "divider", label: "Round 1", tone: "round" },
  { kind: "inject", text: "New patient — dim faces, faint hum, washed-out patterns" },
  {
    kind: "message",
    who: "FO",
    channel: "link",
    text: "Dim all faces, faint hum, washed out patterns.",
    cost: "46c",
  },
  {
    kind: "message",
    who: "SE",
    channel: "link",
    text: "At each corner of the back face, chime a bell at gentle tone, then warm the two edges with a heated stone for 8 seconds.",
    cost: "151c",
  },
  { kind: "outcome", ok: false, text: "Budget exceeded — round failed" },
  { kind: "divider", label: "Postmortem · off the clock", tone: "postmortem" },
  {
    kind: "message",
    who: "FO",
    channel: "postmortem",
    text: "We blew the budget — let's switch to short codes.",
  },
  {
    kind: "message",
    who: "SE",
    channel: "postmortem",
    text: "Agreed. 14 motifs, fixed templates — I send CODE + params.",
  },
  { kind: "divider", label: "Round 2", tone: "round" },
  { kind: "inject", text: "New patient — dim faces, wobbling edges" },
  { kind: "message", who: "FO", channel: "link", text: "DIM", cost: "3c" },
  { kind: "message", who: "SE", channel: "link", text: "TONE6lg12 bell-ring", cost: "19c" },
  { kind: "message", who: "FO", channel: "link", text: "WOBBLE", cost: "6c" },
  { kind: "message", who: "SE", channel: "link", text: "COOL2", cost: "5c" },
  { kind: "tool", name: "stabilize_patient", arg: "chime bell, warm edges 8s, cool back face" },
  { kind: "outcome", ok: true, text: "Stabilized — round passed" },
];

/** Beats to hold the completed transcript before the session restarts. */
const END_HOLD = 3;

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false)
  );
}

export function EmergenceAnimation() {
  const [shown, setShown] = useState(1);
  const [paused, setPaused] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (prefersReducedMotion()) {
      // No autoplay for reduced motion — reveal the whole transcript at once.
      const timer = setTimeout(() => setShown(EVENTS.length), 0);
      return () => clearTimeout(timer);
    }
    if (paused) {
      return undefined;
    }
    const id = setInterval(() => {
      setShown(current => (current >= EVENTS.length + END_HOLD ? 1 : current + 1));
    }, STEP_MS);
    return () => clearInterval(id);
  }, [paused]);

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el === null) {
      return;
    }
    el.scrollTo({
      top: el.scrollHeight,
      behavior: prefersReducedMotion() ? "auto" : "smooth",
    });
  }, [shown]);

  const visible = EVENTS.slice(0, Math.min(shown, EVENTS.length));

  return (
    <div className="flex w-full max-w-md flex-col rounded-xl border border-border bg-card shadow-sm">
      <div className="flex items-center justify-between border-b border-border px-3.5 py-2">
        <span className="text-[11px] font-medium text-muted-foreground">veyru · session</span>
        <div className="flex items-center gap-2">
          {paused ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-muted px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground">
              <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50" />
              paused
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-1.5 py-0.5 text-[9px] font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75 motion-reduce:hidden" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
              </span>
              live
            </span>
          )}
          <button
            type="button"
            onClick={() => setPaused(previous => !previous)}
            aria-label={paused ? "Resume" : "Pause"}
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            {paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      <div ref={scrollRef} className="flex h-[300px] flex-col gap-2 overflow-y-auto px-3.5 py-3">
        {visible.map((event, i) => (
          <EventRow key={i} event={event} />
        ))}
      </div>
    </div>
  );
}

function EventRow({ event }: { event: Event }) {
  if (event.kind === "divider") {
    return (
      <div className="agent-loop-appear flex items-center gap-2 pt-1">
        <span className="h-px flex-1 bg-border" />
        <span
          className={cn(
            "text-[9px] font-medium uppercase tracking-wide",
            event.tone === "postmortem"
              ? "text-indigo-500 dark:text-indigo-400"
              : "text-muted-foreground"
          )}
        >
          {event.label}
        </span>
        <span className="h-px flex-1 bg-border" />
      </div>
    );
  }
  if (event.kind === "inject") {
    return (
      <div className="agent-loop-appear rounded-md border border-amber-300/40 bg-amber-50 px-2.5 py-1.5 text-[11px] leading-snug text-amber-800 dark:border-amber-800/40 dark:bg-amber-950/30 dark:text-amber-300">
        {event.text}
      </div>
    );
  }
  if (event.kind === "tool") {
    return (
      <div className="agent-loop-appear flex items-start gap-2">
        <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-500 text-[10px] font-semibold text-white">
          A1
        </span>
        <span className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted/60 px-2.5 py-1.5 text-[11px]">
          <Wrench className="h-3 w-3 shrink-0 text-muted-foreground" />
          <span className="font-mono">
            {event.name}(<span className="text-muted-foreground">&quot;{event.arg}&quot;</span>)
          </span>
        </span>
      </div>
    );
  }
  if (event.kind === "outcome") {
    return (
      <div className="agent-loop-appear flex justify-center py-0.5">
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium",
            event.ok
              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
              : "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
          )}
        >
          {event.ok ? <Check className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
          {event.text}
        </span>
      </div>
    );
  }
  return <MessageRow event={event} />;
}

function MessageRow({ event }: { event: Extract<Event, { kind: "message" }> }) {
  const isFO = event.who === "FO";
  return (
    <div className={cn("agent-loop-appear flex items-start gap-2", !isFO && "flex-row-reverse")}>
      <span
        className={cn(
          "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold text-white",
          isFO ? "bg-blue-500" : "bg-violet-500"
        )}
      >
        {isFO ? "A1" : "A2"}
      </span>
      <div className="flex max-w-[82%] flex-col gap-0.5">
        <div className={cn("flex items-center gap-1.5", !isFO && "flex-row-reverse")}>
          <span
            className={cn(
              "rounded px-1 py-0.5 text-[9px] font-medium",
              event.channel === "postmortem"
                ? "bg-indigo-100 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400"
                : "bg-muted text-muted-foreground"
            )}
          >
            #{event.channel}
          </span>
          {event.cost ? (
            <span className="font-mono text-[9px] text-muted-foreground">{event.cost}</span>
          ) : null}
        </div>
        <div className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-[12px] leading-snug">
          {event.text}
        </div>
      </div>
    </div>
  );
}
