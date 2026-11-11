"use client";

import type { ReactNode } from "react";
import { Square, Trash2 } from "lucide-react";
import { Modal } from "@/shared/components/ui/modal";
import { splitRunId } from "@/shared/lib/run-id";
import { humanize } from "./format";

/** A run action that cannot be taken back from the UI, so it is confirmed first. */
export type ConfirmableRunAction = "delete" | "stop";

const ACTION_TEXT: Record<
  ConfirmableRunAction,
  { title: string; confirmLabel: string; icon: ReactNode; consequence: ReactNode }
> = {
  delete: {
    title: "Delete this run?",
    confirmLabel: "Delete run",
    icon: <Trash2 className="h-3.5 w-3.5" />,
    consequence: (
      <>
        will leave the runs list for everyone in this group. A simulation still running is stopped
        first. The files move to <span className="font-mono">_trash/</span> in the server&apos;s
        runs directory.
      </>
    ),
  },
  stop: {
    title: "Stop this run?",
    confirmLabel: "Stop run",
    icon: <Square className="h-3.5 w-3.5" />,
    consequence: (
      <>
        ends now, partway through. It keeps what it recorded so far and is marked killed at the
        round it reached.
      </>
    ),
  },
};

/**
 * Asks before a run is deleted or stopped. Confirming calls `onConfirm`; Cancel,
 * Escape and a click on the backdrop call `onCancel`. The text says what the
 * server does: a delete stops a live simulation and moves the run directory to
 * the runs directory's `_trash/`; a stop ends the simulation's process and
 * records the run as killed.
 */
export function ConfirmRunActionModal({
  action,
  runId,
  onConfirm,
  onCancel,
}: {
  action: ConfirmableRunAction;
  runId: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { scenario, run_dir_name } = splitRunId(runId);
  const text = ACTION_TEXT[action];
  return (
    <Modal
      label={text.title}
      width="md"
      panelClassName="flex flex-col gap-3 p-5"
      panelId={null}
      onClose={onCancel}
    >
      <h2 className="text-sm font-medium">{text.title}</h2>
      <p className="text-xs text-muted-foreground">
        {humanize(scenario)} <span className="font-mono">{run_dir_name}</span> {text.consequence}
      </p>
      <div className="flex justify-end gap-2 pt-1">
        <button
          type="button"
          autoFocus
          onClick={onCancel}
          className="rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={onConfirm}
          className="inline-flex items-center gap-1.5 rounded-md bg-destructive px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90"
        >
          {text.icon}
          {text.confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
