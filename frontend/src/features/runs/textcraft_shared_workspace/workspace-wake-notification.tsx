"use client";

import { Bell } from "lucide-react";
import { NotificationChip, type NotificationPayload } from "../notification-display";

/** One notification textcraft drained from the agent's queue when it resumed. */
interface LifecycleEntry {
  type: string;
  text: string | null;
  reason: string | null;
}

/** What textcraft's `read_notifications` returns: `WorkspaceWake` in
 *  `scenarios/textcraft_shared_workspace/tool_results.py`. */
export interface WorkspaceWake {
  type: "wake" | "done";
  wake_reasons: string[];
  round: number;
  waited_seconds: number;
  workspace: string | null;
  lifecycle: LifecycleEntry[];
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === "string");
}

function isLifecycleEntry(value: unknown): value is LifecycleEntry {
  if (typeof value !== "object" || value === null) return false;
  const entry = value as Record<string, unknown>;
  return (
    typeof entry.type === "string" &&
    (typeof entry.text === "string" || entry.text === null) &&
    (typeof entry.reason === "string" || entry.reason === null)
  );
}

/** The payload as a `WorkspaceWake`, or null when it is not shaped like one. */
export function parseWorkspaceWake(payload: NotificationPayload): WorkspaceWake | null {
  if (payload.type !== "wake" && payload.type !== "done") return null;
  const { wake_reasons, round, waited_seconds, workspace, lifecycle } = payload;
  if (!isStringArray(wake_reasons)) return null;
  if (typeof round !== "number" || typeof waited_seconds !== "number") return null;
  if (typeof workspace !== "string" && workspace !== null) return null;
  if (!Array.isArray(lifecycle) || !lifecycle.every(isLifecycleEntry)) return null;
  return { type: payload.type, wake_reasons, round, waited_seconds, workspace, lifecycle };
}

/** The chip for a textcraft wake: why the agent resumed and how long it waited,
 *  the notifications drained from its queue as the platform's chips, and the
 *  workspace view with its first line in the label's weight. */
export function WorkspaceWakeNotification({ wake }: { wake: WorkspaceWake }) {
  const workspaceLines = (wake.workspace ?? "").split("\n").filter(l => l.trim().length > 0);
  const firstLine = workspaceLines[0] ?? "";
  const rest = workspaceLines.slice(1).join("\n");
  return (
    <div className="space-y-1 text-[11px]">
      <div className="flex items-center gap-1.5 rounded border border-border/40 bg-muted/20 px-2 py-1">
        <Bell className="h-3 w-3 shrink-0 text-muted-foreground/70" />
        <span className="text-muted-foreground">
          {wake.type === "done" ? "Run over" : "Woke"}: {wake.wake_reasons.join(", ")}
          {wake.waited_seconds > 0 ? ` after ${wake.waited_seconds.toFixed(1)}s` : ""}
        </span>
      </div>
      {wake.lifecycle.map((entry, index) => (
        <NotificationChip
          key={index}
          payload={{
            type: entry.type,
            text: entry.text ?? undefined,
            reason: entry.reason ?? undefined,
          }}
        />
      ))}
      {workspaceLines.length > 0 ? (
        <div className="rounded border border-amber-200/60 bg-amber-50/40 px-2 py-1 dark:border-amber-800/40 dark:bg-amber-950/20">
          <span className="font-medium text-amber-700 dark:text-amber-300">{firstLine}</span>
          {rest.length > 0 ? (
            <div className="mt-0.5 whitespace-pre-wrap text-amber-600/80 dark:text-amber-400/70">
              {rest}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
