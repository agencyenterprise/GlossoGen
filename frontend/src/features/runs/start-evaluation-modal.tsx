"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { api } from "@/shared/lib/api-client";
import { humanize } from "./format";
import { ModelPicker } from "./model-picker";

export function StartEvaluationModal({
  runId,
  scenarioName,
  onClose,
  onLaunched,
}: {
  runId: string;
  scenarioName: string;
  onClose: () => void;
  onLaunched: () => void;
}) {
  const queryClient = useQueryClient();
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [selectedEvaluators, setSelectedEvaluators] = useState<Set<string>>(new Set());
  const [initialized, setInitialized] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["scenarios"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/scenarios");
      if (error) {
        throw new Error("Failed to fetch scenarios");
      }
      return data;
    },
  });

  // Initialize all evaluators as selected once data loads
  const scenarioInfo = data?.scenarios.find(s => s.scenario_name === scenarioName);
  const availableEvaluators = scenarioInfo?.available_evaluators ?? [];

  if (!initialized && availableEvaluators.length > 0) {
    setSelectedEvaluators(new Set(availableEvaluators));
    setInitialized(true);
  }

  function handleModelSelect(selectedModel: string, selectedProvider: string) {
    setModel(selectedModel);
    setProvider(selectedProvider);
  }

  function toggleEvaluator(name: string) {
    setSelectedEvaluators(prev => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  }

  function selectAll() {
    setSelectedEvaluators(new Set(availableEvaluators));
  }

  function selectNone() {
    setSelectedEvaluators(new Set());
  }

  const startMutation = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/api/runs/{run_id}/evaluate", {
        params: { path: { run_id: runId } },
        body: {
          model,
          provider,
          evaluators: [...selectedEvaluators],
        },
      });
      if (error) {
        const detail =
          typeof error === "object" && error !== null && "detail" in error
            ? String((error as { detail: unknown }).detail)
            : "Failed to start evaluation";
        throw new Error(detail);
      }
    },
    onSuccess: () => {
      onLaunched();
      queryClient.invalidateQueries({ queryKey: ["run", runId] });
      onClose();
    },
  });

  const canSubmit = model && provider && selectedEvaluators.size > 0;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (canSubmit) {
      startMutation.mutate();
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-xl border border-border bg-background p-5 shadow-xl">
        <h3 className="mb-4 text-sm font-medium">Run Evaluation</h3>

        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <ModelPicker
              models={data?.models ?? []}
              selectedModel={model}
              onSelect={handleModelSelect}
            />

            {/* Evaluators */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium">Evaluators</span>
                <span className="flex gap-2 text-[11px] text-muted-foreground">
                  <button type="button" className="hover:text-foreground" onClick={selectAll}>
                    All
                  </button>
                  <button type="button" className="hover:text-foreground" onClick={selectNone}>
                    None
                  </button>
                </span>
              </div>
              <div className="max-h-48 space-y-0.5 overflow-y-auto rounded-md border border-input p-2">
                {availableEvaluators.map(name => (
                  <label
                    key={name}
                    className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-xs transition-colors hover:bg-muted/50"
                  >
                    <input
                      type="checkbox"
                      checked={selectedEvaluators.has(name)}
                      onChange={() => toggleEvaluator(name)}
                      className="rounded border-input"
                    />
                    {humanize(name)}
                  </label>
                ))}
              </div>
            </div>

            {startMutation.error ? (
              <p className="text-xs text-destructive">{startMutation.error.message}</p>
            ) : null}

            {/* Actions */}
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                className="rounded-md border border-border px-3 py-1 text-[12px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                onClick={onClose}
                disabled={startMutation.isPending}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!canSubmit || startMutation.isPending}
                className="inline-flex items-center gap-1.5 rounded-md bg-foreground px-3 py-1 text-[12px] font-medium text-background transition-opacity hover:opacity-80 disabled:opacity-50"
              >
                {startMutation.isPending ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Starting...
                  </>
                ) : (
                  "Start Evaluation"
                )}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
