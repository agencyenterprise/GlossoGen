"use client";

import { useEffect, useState } from "react";
import {
  Bell,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Flag,
  Hash,
  Loader2,
  Play,
  RotateCcw,
  Wrench,
} from "lucide-react";
import { cn } from "@/shared/lib/cn";

/**
 * Looping illustration of the agent loop. Two agents each cycle through their
 * tools — read_notifications, read_channel, send_message — drawn as a real loop.
 * read_notifications "holds" until something happens on #link, then resolves to
 * new_message (or round_ended); read_channel and send_message point to the
 * shared #link channel when called. The choreography is a small JS state machine
 * that steps through a fixed script; the CSS flourishes live in globals.css.
 */

type ToolId = "read_notifications" | "read_channel" | "send_message" | "custom_tool";
type AgentPhase = "hold" | "call" | "result";
type ChannelAction = "send" | "read";
interface AgentBeat {
  tool: ToolId;
  phase: AgentPhase;
  result?: "round_started" | "new_message" | "round_ended";
}
interface LinkMessage {
  who: "FO" | "SE";
  text: string;
}
interface Beat {
  a: AgentBeat;
  b: AgentBeat;
  link: LinkMessage[];
  banner?: "start" | "end";
}

const A1_MSG: LinkMessage = { who: "FO", text: "corners dim…" };
const A2_MSG: LinkMessage = { who: "SE", text: "drape cloth 8s" };
const BEAT_MS = 1700;

/**
 * The looping story. Every turn begins at read_notifications (blocking), but the
 * path afterwards varies: Agent 1 reports straight away with send_message; Agent 2
 * reads the channel first (read_channel) then replies; Agent 1 then runs a
 * scenario-specific custom_tool. Then the round ends and it loops.
 */
const BEATS: Beat[] = [
  {
    a: { tool: "read_notifications", phase: "result", result: "round_started" },
    b: { tool: "read_notifications", phase: "result", result: "round_started" },
    link: [],
    banner: "start",
  },
  {
    a: { tool: "send_message", phase: "call" },
    b: { tool: "read_notifications", phase: "hold" },
    link: [A1_MSG],
  },
  {
    a: { tool: "read_notifications", phase: "hold" },
    b: { tool: "read_notifications", phase: "result", result: "new_message" },
    link: [A1_MSG],
  },
  {
    a: { tool: "read_notifications", phase: "hold" },
    b: { tool: "read_channel", phase: "call" },
    link: [A1_MSG],
  },
  {
    a: { tool: "read_notifications", phase: "hold" },
    b: { tool: "send_message", phase: "call" },
    link: [A1_MSG, A2_MSG],
  },
  {
    a: { tool: "read_notifications", phase: "result", result: "new_message" },
    b: { tool: "read_notifications", phase: "hold" },
    link: [A1_MSG, A2_MSG],
  },
  {
    a: { tool: "custom_tool", phase: "call" },
    b: { tool: "read_notifications", phase: "hold" },
    link: [A1_MSG, A2_MSG],
  },
  {
    a: { tool: "read_notifications", phase: "result", result: "round_ended" },
    b: { tool: "read_notifications", phase: "result", result: "round_ended" },
    link: [],
    banner: "end",
  },
];

export function AgentLoopAnimation() {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const reduce =
      typeof window !== "undefined" &&
      (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
    if (reduce) {
      // Respect reduced-motion: hold on the opening frame, no ticking.
      return undefined;
    }
    const id = setInterval(() => setIndex(i => (i + 1) % BEATS.length), BEAT_MS);
    return () => clearInterval(id);
  }, []);

  const beat = BEATS[index];
  if (beat === undefined) {
    return null;
  }
  const banner = beat.banner ?? null;
  const linkAction = channelAction(beat.a, beat.b);

  return (
    <div className="w-full rounded-xl border border-border bg-card p-5 shadow-sm sm:p-6">
      <div className="grid grid-cols-[minmax(0,1fr)_auto_auto_auto_minmax(0,1fr)] items-center gap-2 sm:gap-3">
        <AgentPanel side="left" who="FO" name="Agent 1" beat={beat.a} />
        <Connector active={usesChannel(beat.a)} action={connAction(beat.a)} who="FO" side="left" />
        <LinkPanel messages={beat.link} banner={banner} action={linkAction} />
        <Connector active={usesChannel(beat.b)} action={connAction(beat.b)} who="SE" side="right" />
        <AgentPanel side="right" who="SE" name="Agent 2" beat={beat.b} />
      </div>
    </div>
  );
}

/** True while the agent is actively reading or sending on the channel. */
function usesChannel(beat: AgentBeat): boolean {
  return beat.phase === "call" && (beat.tool === "read_channel" || beat.tool === "send_message");
}

function connAction(beat: AgentBeat): ChannelAction {
  if (beat.tool === "send_message") {
    return "send";
  }
  return "read";
}

/** The channel action happening this beat (from whichever agent is acting). */
function channelAction(a: AgentBeat, b: AgentBeat): ChannelAction | null {
  for (const beat of [a, b]) {
    if (usesChannel(beat)) {
      return connAction(beat);
    }
  }
  return null;
}

function Avatar({ who }: { who: "FO" | "SE" }) {
  return (
    <span
      className={cn(
        "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold text-white",
        who === "FO" ? "bg-blue-500" : "bg-violet-500"
      )}
    >
      {who === "FO" ? "A1" : "A2"}
    </span>
  );
}

function AgentPanel({
  side,
  who,
  name,
  beat,
}: {
  side: "left" | "right";
  who: "FO" | "SE";
  name: string;
  beat: AgentBeat;
}) {
  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <div
        className={cn(
          "mb-2 flex items-center gap-2",
          side === "right" && "flex-row-reverse text-right"
        )}
      >
        <Avatar who={who} />
        <div className="min-w-0">
          <div className="truncate text-[12px] font-medium leading-tight">{name}</div>
          <div
            className={cn(
              "mt-0.5 flex items-center gap-1 text-[9px] uppercase tracking-wide text-muted-foreground",
              side === "right" && "flex-row-reverse"
            )}
          >
            <RotateCcw className="h-2.5 w-2.5" /> agent loop
          </div>
        </div>
      </div>
      <div className={cn("relative", side === "left" ? "pl-4" : "pr-4")}>
        <LoopBracket side={side} />
        <div className="flex flex-col gap-1">
          <ToolChip tool="read_notifications" beat={beat} side={side} />
          <div
            className={cn(
              "flex items-center gap-1 text-[8px] uppercase tracking-wide text-muted-foreground/50",
              side === "right" ? "flex-row-reverse" : ""
            )}
          >
            <ChevronDown className="h-2.5 w-2.5" /> then any of
          </div>
          <ToolChip tool="read_channel" beat={beat} side={side} />
          <ToolChip tool="send_message" beat={beat} side={side} />
          <ToolChip tool="custom_tool" beat={beat} side={side} />
        </div>
      </div>
    </div>
  );
}

function LoopBracket({ side }: { side: "left" | "right" }) {
  return (
    <div
      aria-hidden
      className={cn(
        "pointer-events-none absolute inset-y-1 w-2.5",
        side === "left" ? "left-0" : "right-0"
      )}
    >
      <div
        className={cn(
          "h-full border-2 border-primary/25",
          side === "left" ? "rounded-l-md border-r-0" : "rounded-r-md border-l-0"
        )}
      />
      <ChevronUp
        className={cn(
          "absolute -top-1 h-3 w-3 text-primary/40",
          side === "left" ? "-left-1" : "-right-1"
        )}
      />
    </div>
  );
}

function ToolChip({ tool, beat, side }: { tool: ToolId; beat: AgentBeat; side: "left" | "right" }) {
  const active = beat.tool === tool;
  return (
    <div
      className={cn(
        "flex items-center gap-1.5 rounded-md border px-2 py-1 font-mono text-[10px] transition-all",
        side === "right" && "flex-row-reverse text-right",
        active
          ? "border-primary/50 bg-primary/5 text-foreground shadow-sm"
          : "border-border bg-muted/40 text-muted-foreground"
      )}
    >
      <span className="truncate">{tool}</span>
      {active ? <StateTag beat={beat} /> : null}
    </div>
  );
}

function StateTag({ beat }: { beat: AgentBeat }) {
  if (beat.tool === "read_notifications") {
    if (beat.phase === "hold") {
      return (
        <Pill className="ml-auto border-border bg-muted text-muted-foreground">
          <Loader2 className="h-2.5 w-2.5 animate-spin" /> blocking
        </Pill>
      );
    }
    if (beat.result === "round_started") {
      return (
        <Pill className="agent-loop-appear ml-auto border-sky-300/50 bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-400">
          <Play className="h-2.5 w-2.5" /> round_started
        </Pill>
      );
    }
    if (beat.result === "round_ended") {
      return (
        <Pill className="agent-loop-appear ml-auto border-amber-300/50 bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
          <Flag className="h-2.5 w-2.5" /> round_ended
        </Pill>
      );
    }
    return (
      <Pill className="agent-loop-appear ml-auto border-emerald-300/50 bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
        <Bell className="h-2.5 w-2.5" /> new_message
      </Pill>
    );
  }
  if (beat.tool === "custom_tool") {
    return (
      <Pill className="ml-auto border-fuchsia-300/50 bg-fuchsia-100 text-fuchsia-700 dark:bg-fuchsia-900/30 dark:text-fuchsia-400">
        <Wrench className="h-2.5 w-2.5" /> run
      </Pill>
    );
  }
  const arrow = beat.tool === "send_message" ? "→" : "←";
  return (
    <Pill className="ml-auto border-sky-300/50 bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-400">
      {arrow} <Hash className="h-2.5 w-2.5" />
      link
    </Pill>
  );
}

function Pill({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full border px-1.5 py-0.5 text-[9px] font-medium",
        className
      )}
    >
      {children}
    </span>
  );
}

function Connector({
  active,
  action,
  who,
  side,
}: {
  active: boolean;
  action: "send" | "read";
  who: "FO" | "SE";
  side: "left" | "right";
}) {
  // The dot flows left→right by default; flip so it always travels toward the
  // acting party's target (channel on send, agent on read).
  const flip = (side === "left" && action === "read") || (side === "right" && action === "send");
  const dotColor = who === "FO" ? "bg-blue-500" : "bg-violet-500";
  const lineColor = who === "FO" ? "bg-blue-500/40" : "bg-violet-500/40";
  const chevronColor = who === "FO" ? "text-blue-500" : "text-violet-500";
  return (
    <div className="flex w-7 items-center sm:w-10">
      <div
        className={cn(
          "relative h-0.5 w-full rounded",
          active ? lineColor : "bg-border/60",
          flip && "-scale-x-100"
        )}
      >
        {active ? (
          <>
            <span
              className={cn(
                "agent-loop-conn-dot absolute top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full",
                dotColor
              )}
            />
            <ChevronRight
              className={cn("absolute -right-1 top-1/2 h-3 w-3 -translate-y-1/2", chevronColor)}
            />
          </>
        ) : null}
      </div>
    </div>
  );
}

function LinkPanel({
  messages,
  banner,
  action,
}: {
  messages: LinkMessage[];
  banner: "start" | "end" | null;
  action: ChannelAction | null;
}) {
  return (
    <div className="w-32 sm:w-44">
      <div className="mb-1.5 flex items-center justify-center gap-1 text-[11px] font-medium text-muted-foreground">
        <Hash className="h-3 w-3" /> link
      </div>
      <div className="flex min-h-[96px] flex-col justify-center gap-1.5 rounded-lg border border-border bg-muted/30 p-2">
        {banner === "start" ? (
          <span className="agent-loop-appear mx-auto inline-flex items-center gap-1 rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-medium text-sky-700 dark:bg-sky-900/30 dark:text-sky-400">
            <Play className="h-3 w-3" /> round started
          </span>
        ) : banner === "end" ? (
          <span className="agent-loop-appear mx-auto inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
            <Flag className="h-3 w-3" /> round ended
          </span>
        ) : messages.length === 0 ? (
          <span className="text-center text-[10px] text-muted-foreground/60">no messages yet…</span>
        ) : (
          messages.map((message, i) => {
            const isNewest = i === messages.length - 1;
            // read_channel pulses every message being read; send_message glows
            // the message that just arrived.
            const emphasis =
              action === "read"
                ? "agent-loop-msg-read"
                : action === "send" && isNewest
                  ? "agent-loop-msg-arrive"
                  : "";
            return (
              <div
                key={`${message.who}-${i}`}
                className="agent-loop-appear flex items-center gap-1.5"
              >
                <span
                  className={cn(
                    "h-2 w-2 shrink-0 rounded-full",
                    message.who === "FO" ? "bg-blue-500" : "bg-violet-500"
                  )}
                />
                <span
                  className={cn(
                    "truncate rounded-md border border-border bg-background px-1.5 py-0.5 text-[10px]",
                    emphasis
                  )}
                >
                  {message.text}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
