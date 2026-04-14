"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, X } from "lucide-react";
import { api } from "@/shared/lib/api-client";

export function NoteEditorModal({
  runId,
  initialContent,
  onClose,
}: {
  runId: string;
  initialContent: string | null;
  onClose: () => void;
}) {
  const [content, setContent] = useState(initialContent ?? "");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async (text: string) => {
      await api.PUT("/api/runs/{run_id}/note", {
        params: { path: { run_id: runId } },
        body: { content: text },
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      queryClient.invalidateQueries({ queryKey: ["run", runId] });
      queryClient.invalidateQueries({ queryKey: ["run-note", runId] });
      onClose();
    },
  });

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return createPortal(
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/50" onClick={onClose}>
      <div className="flex min-h-full items-center justify-center p-4">
        <div
          className="flex w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-border bg-background shadow-xl"
          onClick={e => e.stopPropagation()}
        >
          <div className="flex items-center justify-between border-b border-border px-5 py-2.5">
            <span className="text-sm font-medium">{initialContent ? "Edit Note" : "Add Note"}</span>
            <button
              aria-label="Close"
              className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted"
              onClick={onClose}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="px-5 py-3">
            <textarea
              className="w-full rounded-md border border-border bg-muted/30 px-3 py-2 font-mono text-xs leading-relaxed text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              rows={12}
              value={content}
              onChange={e => setContent(e.target.value)}
              placeholder="Write your note in markdown..."
              autoFocus
            />
          </div>
          <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-2.5">
            <button
              type="button"
              className="rounded-md px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
              disabled={mutation.isPending}
              onClick={() => mutation.mutate(content)}
            >
              {mutation.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
              Save
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
