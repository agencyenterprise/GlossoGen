"use client";

import { Trash2 } from "lucide-react";
import { Modal } from "@/shared/components/ui/modal";
import { splitRunId } from "@/shared/lib/run-id";
import { humanize } from "./format";

/**
 * Asks before a run is deleted from the runs list. Confirming calls
 * `onConfirm`; Cancel, Escape and a click on the backdrop call `onCancel`.
 * The server stops a live simulation and moves the run directory to the runs
 * directory's `_trash/`, so the dialog says the run leaves every listing.
 */
export function DeleteRunModal({
  runId,
  onConfirm,
  onCancel,
}: {
  runId: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { scenario, run_dir_name } = splitRunId(runId);
  return (
    <Modal
      label="Delete run"
      width="md"
      panelClassName="flex flex-col gap-3 p-5"
      panelId={null}
      onClose={onCancel}
    >
      <h2 className="text-sm font-medium">Delete this run?</h2>
      <p className="text-xs text-muted-foreground">
        {humanize(scenario)} <span className="font-mono">{run_dir_name}</span> will leave the runs
        list for everyone in this group. A simulation still running is stopped first. The files move
        to <span className="font-mono">_trash/</span> in the server&apos;s runs directory.
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
          <Trash2 className="h-3.5 w-3.5" />
          Delete run
        </button>
      </div>
    </Modal>
  );
}
