"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/shared/lib/api-client";
import { humanize } from "./format";

type KnobsMap = Record<string, unknown>;

function KnobsBadges({
  knobs,
  onChange,
}: {
  knobs: KnobsMap;
  onChange: (updated: KnobsMap) => void;
}) {
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");

  function startEditing(key: string) {
    setEditingKey(key);
    setEditValue(JSON.stringify(knobs[key]));
  }

  function commitEdit(key: string) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(editValue);
    } catch {
      parsed = editValue;
    }
    onChange({ ...knobs, [key]: parsed });
    setEditingKey(null);
  }

  function handleKeyDown(e: React.KeyboardEvent, key: string) {
    if (e.key === "Enter") {
      e.preventDefault();
      commitEdit(key);
    }
    if (e.key === "Escape") {
      setEditingKey(null);
    }
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {Object.entries(knobs).map(([key, value]) => {
        if (editingKey === key) {
          return (
            <span
              key={key}
              className="inline-flex items-center gap-1 rounded border border-primary bg-primary/5 px-1.5 py-0.5 text-[11px]"
            >
              <span className="text-muted-foreground">{humanize(key)}</span>
              <input
                autoFocus
                value={editValue}
                onChange={e => setEditValue(e.target.value)}
                onBlur={() => commitEdit(key)}
                onKeyDown={e => handleKeyDown(e, key)}
                className="w-20 rounded border border-input bg-background px-1 py-0 text-[11px] font-medium outline-none focus:border-primary"
              />
            </span>
          );
        }

        const displayValue =
          typeof value === "object" && value !== null ? JSON.stringify(value) : String(value);

        return (
          <button
            key={key}
            type="button"
            onClick={() => startEditing(key)}
            className="inline-flex items-center gap-0.5 rounded border border-border bg-muted/50 px-1.5 py-0.5 text-[11px] transition-colors hover:border-primary hover:bg-primary/5"
          >
            <span className="text-muted-foreground">{humanize(key)}</span>
            <span className="font-medium">{displayValue}</span>
          </button>
        );
      })}
    </div>
  );
}

export function NewSimulationForm() {
  const router = useRouter();
  const [scenario, setScenario] = useState("");
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [knobsFile, setKnobsFile] = useState("");
  const [knobs, setKnobs] = useState<KnobsMap | null>(null);

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

  const knobsQuery = useQuery({
    queryKey: ["knobs", scenario, knobsFile],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/scenarios/{scenario_name}/knobs/{knobs_name}", {
        params: { path: { scenario_name: scenario, knobs_name: knobsFile } },
      });
      if (error) {
        throw new Error("Failed to fetch knobs");
      }
      setKnobs({ ...data.knobs });
      return data;
    },
    enabled: !!scenario && !!knobsFile,
  });

  const startMutation = useMutation({
    mutationFn: async () => {
      // Snapshot existing run IDs so we can detect the new one.
      const before = await api.GET("/api/runs");
      const existingIds = new Set((before.data?.runs ?? []).map(r => r.run_id));

      const { error } = await api.POST("/api/runs/start", {
        body: {
          scenario_name: scenario,
          model,
          provider,
          knobs: knobs ?? null,
        },
      });
      if (error) {
        const detail =
          typeof error === "object" && error !== null && "detail" in error
            ? String((error as { detail: unknown }).detail)
            : "Failed to start simulation";
        throw new Error(detail);
      }

      // Poll until the new run appears in the runs list.
      const deadline = Date.now() + 30_000;
      while (Date.now() < deadline) {
        await new Promise(r => setTimeout(r, 1000));
        const after = await api.GET("/api/runs");
        const newRun = (after.data?.runs ?? []).find(r => !existingIds.has(r.run_id));
        if (newRun) {
          return newRun.run_id;
        }
      }
      throw new Error("Simulation did not appear within 30 seconds");
    },
    onSuccess: runId => {
      router.push(`/runs/${runId}`);
    },
  });

  const selectedScenario = data?.scenarios.find(s => s.scenario_name === scenario);
  const knobsFiles = selectedScenario?.knobs_files ?? [];
  const needsKnobs = knobsFiles.length > 0;
  const filteredModels = data?.models.filter(m => m.provider === provider) ?? [];
  const canSubmit = scenario && model && provider && (!needsKnobs || knobs);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  function handleScenarioChange(value: string) {
    setScenario(value);
    setKnobsFile("");
    setKnobs(null);
  }

  function handleProviderChange(value: string) {
    setProvider(value);
    setModel("");
  }

  function handleKnobsFileChange(value: string) {
    setKnobsFile(value);
    if (!value) {
      setKnobs(null);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (canSubmit) {
      startMutation.mutate();
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="space-y-2">
        <label htmlFor="scenario" className="block text-sm font-medium">
          Scenario
        </label>
        <select
          id="scenario"
          value={scenario}
          onChange={e => handleScenarioChange(e.target.value)}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
        >
          <option value="">Select a scenario...</option>
          {data?.scenarios.map(s => (
            <option key={s.scenario_name} value={s.scenario_name}>
              {humanize(s.scenario_name)}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-2">
        <label htmlFor="provider" className="block text-sm font-medium">
          Provider
        </label>
        <select
          id="provider"
          value={provider}
          onChange={e => handleProviderChange(e.target.value)}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
        >
          <option value="">Select a provider...</option>
          {data?.providers.map(p => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-2">
        <label htmlFor="model" className="block text-sm font-medium">
          Model
        </label>
        <select
          id="model"
          value={model}
          onChange={e => setModel(e.target.value)}
          disabled={!provider}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm disabled:bg-muted disabled:text-muted-foreground"
        >
          {provider ? (
            <>
              <option value="">Select a model...</option>
              {filteredModels.map(m => (
                <option key={m.model_prefix} value={m.model_prefix}>
                  {m.model_prefix}
                </option>
              ))}
            </>
          ) : (
            <option value="">Select a provider first</option>
          )}
        </select>
      </div>

      <div className="space-y-2">
        <label htmlFor="knobs" className="block text-sm font-medium">
          Knobs
        </label>
        {needsKnobs ? (
          <select
            id="knobs"
            value={knobsFile}
            onChange={e => handleKnobsFileChange(e.target.value)}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          >
            <option value="">Select a knobs preset...</option>
            {knobsFiles.map(f => (
              <option key={f} value={f}>
                {humanize(f.replace("knobs_", ""))}
              </option>
            ))}
          </select>
        ) : (
          <select
            id="knobs"
            disabled
            className="w-full rounded-md border border-input bg-muted px-3 py-2 text-sm text-muted-foreground"
          >
            <option>No knobs for this scenario</option>
          </select>
        )}

        {knobs ? (
          <div className="pt-1">
            <KnobsBadges knobs={knobs} onChange={setKnobs} />
          </div>
        ) : null}

        {knobsQuery.isLoading ? (
          <div className="flex items-center gap-2 pt-1 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            Loading knobs...
          </div>
        ) : null}
      </div>

      {startMutation.error ? (
        <p className="text-sm text-destructive">{startMutation.error.message}</p>
      ) : null}

      <div className="flex items-center justify-between pt-2">
        <Link
          href="/runs"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to runs
        </Link>
        <button
          type="submit"
          disabled={!canSubmit || startMutation.isPending}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50 disabled:pointer-events-none"
        >
          {startMutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Starting...
            </>
          ) : (
            "Start Simulation"
          )}
        </button>
      </div>
    </form>
  );
}
