"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, Plus, X } from "lucide-react";
import { api } from "@/shared/lib/api-client";

const LABEL_COLORS = [
  { bg: "bg-blue-100 dark:bg-blue-900/30", text: "text-blue-700 dark:text-blue-400" },
  { bg: "bg-amber-100 dark:bg-amber-900/30", text: "text-amber-700 dark:text-amber-400" },
  { bg: "bg-emerald-100 dark:bg-emerald-900/30", text: "text-emerald-700 dark:text-emerald-400" },
  { bg: "bg-rose-100 dark:bg-rose-900/30", text: "text-rose-700 dark:text-rose-400" },
  { bg: "bg-purple-100 dark:bg-purple-900/30", text: "text-purple-700 dark:text-purple-400" },
  { bg: "bg-cyan-100 dark:bg-cyan-900/30", text: "text-cyan-700 dark:text-cyan-400" },
  { bg: "bg-orange-100 dark:bg-orange-900/30", text: "text-orange-700 dark:text-orange-400" },
  { bg: "bg-pink-100 dark:bg-pink-900/30", text: "text-pink-700 dark:text-pink-400" },
];

const EVAL_IDENTIFIED_COLOR = {
  bg: "bg-emerald-100 dark:bg-emerald-900/30",
  text: "text-emerald-700 dark:text-emerald-400",
};

const EVAL_PARTIAL_COLOR = {
  bg: "bg-amber-100 dark:bg-amber-900/30",
  text: "text-amber-700 dark:text-amber-400",
};

const EVAL_FAIL_COLOR = {
  bg: "bg-rose-100 dark:bg-rose-900/30",
  text: "text-rose-700 dark:text-rose-400",
};

export function labelColor(label: string): (typeof LABEL_COLORS)[number] {
  if (label.startsWith("eval:")) {
    if (label.endsWith(":identified")) {
      return EVAL_IDENTIFIED_COLOR;
    }
    if (label.endsWith(":partial")) {
      return EVAL_PARTIAL_COLOR;
    }
    if (label.endsWith(":fail")) {
      return EVAL_FAIL_COLOR;
    }
  }

  let hash = 0;
  for (let i = 0; i < label.length; i++) {
    hash = (hash * 31 + label.charCodeAt(i)) | 0;
  }
  return LABEL_COLORS[Math.abs(hash) % LABEL_COLORS.length]!;
}

export function LabelPickerModal({
  runId,
  currentLabels,
  onClose,
}: {
  runId: string;
  currentLabels: string[];
  onClose: () => void;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set(currentLabels));
  const [newLabel, setNewLabel] = useState("");
  const queryClient = useQueryClient();

  const { data: allLabelsData } = useQuery({
    queryKey: ["all-labels"],
    queryFn: async () => {
      const { data: resp } = await api.GET("/api/labels");
      return resp;
    },
  });

  const mutation = useMutation({
    mutationFn: async (labels: string[]) => {
      await api.PUT("/api/runs/{run_id}/labels", {
        params: { path: { run_id: runId } },
        body: { labels },
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      queryClient.invalidateQueries({ queryKey: ["run", runId] });
      queryClient.invalidateQueries({ queryKey: ["all-labels"] });
    },
  });

  function toggleLabel(label: string) {
    const next = new Set(selected);
    if (next.has(label)) {
      next.delete(label);
    } else {
      next.add(label);
    }
    setSelected(next);
    mutation.mutate(Array.from(next).sort());
  }

  function addNewLabel() {
    const trimmed = newLabel.trim().toLowerCase();
    if (!trimmed || selected.has(trimmed)) {
      return;
    }
    const next = new Set(selected);
    next.add(trimmed);
    setSelected(next);
    setNewLabel("");
    mutation.mutate(Array.from(next).sort());
  }

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const allLabels = allLabelsData?.labels ?? [];
  const combined = Array.from(new Set([...allLabels, ...selected])).sort();

  return createPortal(
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/50" onClick={onClose}>
      <div className="flex min-h-full items-center justify-center p-4">
        <div
          className="flex w-full max-w-sm flex-col overflow-hidden rounded-xl border border-border bg-background shadow-xl"
          onClick={e => e.stopPropagation()}
        >
          <div className="flex items-center justify-between border-b border-border px-5 py-2.5">
            <span className="text-sm font-medium">Labels</span>
            <button
              aria-label="Close"
              className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted"
              onClick={onClose}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="max-h-64 overflow-y-auto px-5 py-2">
            {combined.length === 0 ? (
              <p className="py-3 text-center text-xs text-muted-foreground">
                No labels yet. Create one below.
              </p>
            ) : null}
            {combined.map(label => {
              const isSelected = selected.has(label);
              const color = labelColor(label);
              return (
                <button
                  key={label}
                  type="button"
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-muted"
                  onClick={() => toggleLabel(label)}
                >
                  <span
                    className={`flex h-4 w-4 items-center justify-center rounded border ${
                      isSelected
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border"
                    }`}
                  >
                    {isSelected ? <Check className="h-3 w-3" /> : null}
                  </span>
                  <span
                    className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium ${color.bg} ${color.text}`}
                  >
                    {label}
                  </span>
                </button>
              );
            })}
          </div>
          <div className="border-t border-border px-5 py-2.5">
            <form
              className="flex items-center gap-2"
              onSubmit={e => {
                e.preventDefault();
                addNewLabel();
              }}
            >
              <input
                type="text"
                className="flex-1 rounded-md border border-border bg-muted/30 px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                placeholder="New label..."
                value={newLabel}
                onChange={e => setNewLabel(e.target.value)}
                autoFocus
              />
              <button
                type="submit"
                className="inline-flex items-center gap-1 rounded-md bg-primary px-2 py-1 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
                disabled={!newLabel.trim()}
              >
                <Plus className="h-3 w-3" />
                Add
              </button>
            </form>
            {mutation.isPending ? (
              <div className="mt-1.5 flex items-center gap-1 text-[10px] text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                Saving...
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
