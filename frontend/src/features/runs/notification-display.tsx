"use client";

import { CheckCircle2, Info, Mail, Moon } from "lucide-react";

/**
 * Notification types returned by the read_notifications MCP tool.
 * Must match the NotificationType enum in activity_notification.py.
 */
export const NOTIFICATION_TYPE = {
  NEW_MESSAGES: "new_messages",
  NEW_INFO: "new_info",
  DONE: "done",
  NO_ACTIVITY: "no_activity",
} as const;

export type NotificationType = (typeof NOTIFICATION_TYPE)[keyof typeof NOTIFICATION_TYPE];

/** The tool name used by all scenarios for reading notifications. */
export const TOOL_NAME_READ_NOTIFICATIONS = "read_notifications";

/** Parsed notification payload from the tool result JSON. */
interface NotificationPayload {
  type: NotificationType;
  channels?: string[];
  text?: string;
  reason?: string;
  detail?: string;
}

/** Try to parse the tool result string as a notification payload. */
export function parseNotificationResult(result: string | null): NotificationPayload | null {
  if (!result) {
    return null;
  }
  // New runs use JSON; old runs use Python repr (single quotes).
  // Try JSON first, then fall back to converting Python repr to JSON.
  const jsonString = result.includes('"type"') ? result : result.replace(/'/g, '"');
  try {
    const parsed: unknown = JSON.parse(jsonString);
    if (typeof parsed === "object" && parsed !== null && "type" in parsed) {
      return parsed as NotificationPayload;
    }
    return null;
  } catch {
    return null;
  }
}

interface NotificationDisplayProps {
  result: string | null;
}

/** Renders a read_notifications result as a compact, type-specific inline display.
 *  Returns null when the result cannot be parsed, so the caller can fall back. */
export function NotificationDisplay({ result }: NotificationDisplayProps) {
  const payload = parseNotificationResult(result);
  if (!payload) {
    return null;
  }

  switch (payload.type) {
    case NOTIFICATION_TYPE.NEW_MESSAGES:
      return <NewMessagesNotification channels={payload.channels ?? []} />;
    case NOTIFICATION_TYPE.NEW_INFO:
      return <NewInfoNotification text={payload.text ?? ""} />;
    case NOTIFICATION_TYPE.DONE:
      return <DoneNotification reason={payload.reason ?? ""} />;
    case NOTIFICATION_TYPE.NO_ACTIVITY:
      return <NoActivityNotification />;
    default:
      return null;
  }
}

function NewMessagesNotification({ channels }: { channels: string[] }) {
  return (
    <div className="flex items-center gap-1.5 rounded border border-blue-200/60 bg-blue-50/40 px-2 py-1 text-[11px] dark:border-blue-800/40 dark:bg-blue-950/20">
      <Mail className="h-3 w-3 shrink-0 text-blue-500 dark:text-blue-400" />
      <span className="text-blue-700 dark:text-blue-300">
        New messages in{" "}
        {channels.map((ch, i) => (
          <span key={ch}>
            {i > 0 ? ", " : ""}
            <span className="font-medium">#{ch}</span>
          </span>
        ))}
      </span>
    </div>
  );
}

function NewInfoNotification({ text }: { text: string }) {
  // Extract just the first meaningful line for the collapsed display
  const lines = text.split("\n").filter(l => l.trim().length > 0);
  const firstLine = lines[0] ?? "";
  const hasMore = lines.length > 1;

  return (
    <div className="rounded border border-amber-200/60 bg-amber-50/40 px-2 py-1 text-[11px] dark:border-amber-800/40 dark:bg-amber-950/20">
      <div className="flex items-start gap-1.5">
        <Info className="mt-0.5 h-3 w-3 shrink-0 text-amber-500 dark:text-amber-400" />
        <div className="min-w-0 flex-1">
          <span className="font-medium text-amber-700 dark:text-amber-300">{firstLine}</span>
          {hasMore ? (
            <div className="mt-0.5 whitespace-pre-wrap text-amber-600/80 dark:text-amber-400/70">
              {lines.slice(1).join("\n")}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function DoneNotification({ reason }: { reason: string }) {
  return (
    <div className="flex items-center gap-1.5 rounded border border-emerald-200/60 bg-emerald-50/40 px-2 py-1 text-[11px] dark:border-emerald-800/40 dark:bg-emerald-950/20">
      <CheckCircle2 className="h-3 w-3 shrink-0 text-emerald-500 dark:text-emerald-400" />
      <span className="text-emerald-700 dark:text-emerald-300">
        Simulation ended{reason ? `: ${reason}` : ""}
      </span>
    </div>
  );
}

function NoActivityNotification() {
  return (
    <div className="flex items-center gap-1.5 rounded border border-border/40 bg-muted/20 px-2 py-1 text-[11px]">
      <Moon className="h-3 w-3 shrink-0 text-muted-foreground/50" />
      <span className="text-muted-foreground/60">No activity</span>
    </div>
  );
}
