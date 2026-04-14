"use client";

import { useEffect } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import { Loader2, X } from "lucide-react";
import { api } from "@/shared/lib/api-client";
import { ProseMarkdown } from "./prose-markdown";

export function NoteViewModal({ runId, onClose }: { runId: string; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ["run-note", runId],
    queryFn: async () => {
      const { data: resp } = await api.GET("/api/runs/{run_id}/note", {
        params: { path: { run_id: runId } },
      });
      return resp;
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
            <span className="text-sm font-medium">Note</span>
            <button
              aria-label="Close"
              className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted"
              onClick={onClose}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="overflow-y-auto px-5 py-3" style={{ maxHeight: "calc(100vh - 6rem)" }}>
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : data?.content ? (
              <ProseMarkdown>{data.content}</ProseMarkdown>
            ) : (
              <p className="py-4 text-center text-xs text-muted-foreground">No note</p>
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
