"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Loader2, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/shared/lib/api-client";
import { formatConfigValueFull, humanize } from "./format";
import { ModelPicker } from "./model-picker";
import { ConfigValueModal } from "./config-value-modal";

type KnobsMap = Record<string, unknown>;

type ModelOverride = { model: string; provider: string };
type KnobPreview = { key: string; value: string };

const MAX_INLINE_KNOB_VALUE_CHARS = 48;

function formatKnobValue(value: unknown): string {
  if (typeof value === "object" && value !== null) {
    return JSON.stringify(value);
  }
  return String(value);
}

function KnobsBadges({
  knobs,
  onChange,
}: {
  knobs: KnobsMap;
  onChange: (updated: KnobsMap) => void;
}) {
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [preview, setPreview] = useState<KnobPreview | null>(null);

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
    <>
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

          const displayValue = formatKnobValue(value);
          const isLongValue = displayValue.length > MAX_INLINE_KNOB_VALUE_CHARS;

          return (
            <button
              key={key}
              type="button"
              onClick={() => {
                if (isLongValue) {
                  setPreview({ key, value: formatConfigValueFull(value) });
                  return;
                }
                startEditing(key);
              }}
              className="inline-flex max-w-full items-center gap-0.5 rounded border border-border bg-muted/50 px-1.5 py-0.5 text-[11px] transition-colors hover:border-primary hover:bg-primary/5"
            >
              <span className="shrink-0 text-muted-foreground">{humanize(key)}</span>
              <span className="max-w-64 truncate font-medium">{displayValue}</span>
            </button>
          );
        })}
      </div>
      {preview ? (
        <ConfigValueModal
          configKey={preview.key}
          value={preview.value}
          onClose={() => setPreview(null)}
          secondaryAction={{
            label: "Edit value",
            onClick: () => {
              const key = preview.key;
              setPreview(null);
              startEditing(key);
            },
          }}
        />
      ) : null}
    </>
  );
}

function AgentModelOverrides({
  agents,
  models,
  overrides,
  onChange,
}: {
  agents: { agent_id: string; role_name: string }[];
  models: { model_prefix: string; provider: string }[];
  overrides: Record<string, ModelOverride>;
  onChange: (updated: Record<string, ModelOverride>) => void;
}) {
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);

  function handleSelect(agentId: string, selectedModel: string, selectedProvider: string) {
    onChange({ ...overrides, [agentId]: { model: selectedModel, provider: selectedProvider } });
    setExpandedAgent(null);
  }

  function handleClear(agentId: string) {
    const next = { ...overrides };
    delete next[agentId];
    onChange(next);
    setExpandedAgent(null);
  }

  return (
    <div className="space-y-1">
      {agents.map(agent => {
        const override = overrides[agent.agent_id];
        const isExpanded = expandedAgent === agent.agent_id;

        return (
          <div key={agent.agent_id} className="rounded border border-border bg-muted/20 px-3 py-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">{agent.role_name}</span>
              <div className="flex items-center gap-2">
                {override ? (
                  <>
                    <span className="text-xs text-primary">
                      {override.provider}/{override.model}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleClear(agent.agent_id)}
                      className="text-muted-foreground transition-colors hover:text-destructive"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    onClick={() => setExpandedAgent(isExpanded ? null : agent.agent_id)}
                    className="text-xs text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {isExpanded ? "Cancel" : "Override"}
                  </button>
                )}
              </div>
            </div>
            {isExpanded ? (
              <div className="mt-2">
                <ModelPicker
                  models={models}
                  selectedModel=""
                  onSelect={(m, p) => handleSelect(agent.agent_id, m, p)}
                />
              </div>
            ) : null}
          </div>
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
  const [modelOverrides, setModelOverrides] = useState<Record<string, ModelOverride>>({});

  function handleModelSelect(selectedModel: string, selectedProvider: string) {
    setModel(selectedModel);
    setProvider(selectedProvider);
  }
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

  const selectedScenario = data?.scenarios.find(s => s.scenario_name === scenario);
  const knobsFiles = selectedScenario?.knobs_files ?? [];
  const needsKnobs = knobsFiles.length > 0;

  const agentRolesQuery = useQuery({
    queryKey: ["agentRoles", scenario, knobs],
    queryFn: async () => {
      const { data, error } = await api.POST("/api/scenarios/{scenario_name}/agents", {
        params: { path: { scenario_name: scenario } },
        body: { knobs: knobs ?? null },
      });
      if (error) {
        throw new Error("Failed to fetch agent roles");
      }
      return data;
    },
    enabled: !!scenario && (!needsKnobs || !!knobs),
  });

  const startMutation = useMutation({
    mutationFn: async () => {
      // Snapshot existing run IDs so we can detect the new one.
      const before = await api.GET("/api/runs");
      const existingIds = new Set((before.data?.runs ?? []).map(r => r.run_id));

      const overridesPayload =
        Object.keys(modelOverrides).length > 0
          ? Object.fromEntries(
              Object.entries(modelOverrides).map(([agentId, ov]) => [
                agentId,
                { model: ov.model, provider: ov.provider },
              ])
            )
          : null;
      let knobsPayload: KnobsMap | null = knobs ? { ...knobs } : null;
      if (overridesPayload !== null) {
        if (knobsPayload === null) {
          knobsPayload = {};
        }
        knobsPayload.model_overrides = overridesPayload;
      }

      const { error } = await api.POST("/api/runs/start", {
        body: {
          scenario_name: scenario,
          model,
          provider,
          knobs: knobsPayload,
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
    setModelOverrides({});
  }

  function handleKnobsFileChange(value: string) {
    setKnobsFile(value);
    if (!value) {
      setKnobs(null);
    }
    setModelOverrides({});
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (canSubmit) {
      startMutation.mutate();
    }
  }

  const agentRoles = agentRolesQuery.data?.agents ?? [];

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

      <ModelPicker models={data?.models ?? []} selectedModel={model} onSelect={handleModelSelect} />

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

      {agentRoles.length > 0 ? (
        <div className="space-y-2">
          <label className="block text-sm font-medium">Agent Model Overrides</label>
          <p className="text-xs text-muted-foreground">
            Optionally override the model for individual agents.
          </p>
          <AgentModelOverrides
            agents={agentRoles}
            models={data?.models ?? []}
            overrides={modelOverrides}
            onChange={setModelOverrides}
          />
        </div>
      ) : null}

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
