"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/shared/lib/api-client";
import { splitRunId } from "@/shared/lib/run-id";
import { formatConfigValueFull, humanize } from "./format";
import { ModelPicker } from "./model-picker";
import { ConfigValueModal } from "./config-value-modal";
import { AgentModelOverrides, type AgentModelOverride } from "./agent-model-overrides";
import { labelColor } from "./label-picker-modal";
import {
  PhaseBuilder,
  buildScheduledEvents,
  computeRoundCount,
  emptyPhaseBuilderState,
  validatePhaseBuilder,
  type PhaseBuilderState,
} from "./phase-builder";
import { VeyruKnobsForm } from "./veyru/veyru-knobs-form";
import {
  buildPayload as buildVeyruPayload,
  validateState as validateVeyruState,
  type VeyruKnobsState,
} from "./veyru/veyru-knobs-state";

const VEYRU_SCENARIO = "veyru";

type KnobsMap = Record<string, unknown>;
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

export function NewSimulationForm() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [scenario, setScenario] = useState("");
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [modelOverrides, setModelOverrides] = useState<Record<string, AgentModelOverride>>({});

  function handleModelSelect(selectedModel: string, selectedProvider: string) {
    setModel(selectedModel);
    setProvider(selectedProvider);
  }
  const [knobsFile, setKnobsFile] = useState("");
  const [knobs, setKnobs] = useState<KnobsMap | null>(null);
  const [veyruState, setVeyruState] = useState<VeyruKnobsState | null>(null);
  const [phaseBuilder, setPhaseBuilder] = useState<PhaseBuilderState>(emptyPhaseBuilderState());
  const [labels, setLabels] = useState<string[]>([]);
  const [labelInput, setLabelInput] = useState("");
  const [note, setNote] = useState("");

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

  const allLabelsQuery = useQuery({
    queryKey: ["all-labels"],
    queryFn: async () => {
      const { data: resp } = await api.GET("/api/labels");
      return resp;
    },
  });

  const isVeyru = scenario === VEYRU_SCENARIO;

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
    enabled: !!scenario && !!knobsFile && !isVeyru,
  });

  const selectedScenario = data?.scenarios.find(s => s.scenario_name === scenario);
  const knobsFiles = selectedScenario?.knobs_files ?? [];
  const needsKnobs = knobsFiles.length > 0;
  const hasSelectedModel = model !== "" && provider !== "";

  const effectiveKnobsForAgents = useMemo<KnobsMap | null>(() => {
    if (isVeyru) {
      if (!veyruState) {
        return null;
      }
      return buildVeyruPayload({ state: veyruState, modelOverrides: {} });
    }
    return knobs;
  }, [isVeyru, veyruState, knobs]);

  const agentRolesQuery = useQuery({
    queryKey: ["agentRoles", scenario, effectiveKnobsForAgents],
    queryFn: async () => {
      const { data, error } = await api.POST("/api/scenarios/{scenario_name}/agents", {
        params: { path: { scenario_name: scenario } },
        body: { knobs: effectiveKnobsForAgents },
      });
      if (error) {
        throw new Error("Failed to fetch agent roles");
      }
      return data;
    },
    enabled: !!scenario && (!needsKnobs || !!effectiveKnobsForAgents),
  });

  const veyruErrors = useMemo(() => {
    if (!isVeyru || !veyruState) {
      return [];
    }
    return validateVeyruState(veyruState);
  }, [isVeyru, veyruState]);

  const startMutation = useMutation({
    mutationFn: async () => {
      // Snapshot existing run IDs so we can detect the new one.
      const before = await api.GET("/api/runs");
      const existingIds = new Set((before.data?.runs ?? []).map(r => r.run_id));

      let knobsPayload: KnobsMap | null;
      if (isVeyru) {
        if (!veyruState) {
          throw new Error("Veyru settings have not loaded yet");
        }
        knobsPayload = buildVeyruPayload({ state: veyruState, modelOverrides });
      } else {
        knobsPayload = knobs ? { ...knobs } : null;
        if (Object.keys(modelOverrides).length > 0) {
          const overridesPayload = Object.fromEntries(
            Object.entries(modelOverrides).map(([agentId, ov]) => [
              agentId,
              { model: ov.model, provider: ov.provider },
            ])
          );
          if (knobsPayload === null) {
            knobsPayload = {};
          }
          knobsPayload.model_overrides = overridesPayload;
        }
      }

      const scheduledEvents = buildScheduledEvents(phaseBuilder);
      if (scheduledEvents.length > 0) {
        if (knobsPayload === null) {
          knobsPayload = {};
        }
        knobsPayload.scheduled_events = scheduledEvents;
        knobsPayload.round_count = computeRoundCount(phaseBuilder);
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
      let newRunId: string | null = null;
      while (Date.now() < deadline) {
        await new Promise(r => setTimeout(r, 1000));
        const after = await api.GET("/api/runs");
        const newRun = (after.data?.runs ?? []).find(r => !existingIds.has(r.run_id));
        if (newRun) {
          newRunId = newRun.run_id;
          break;
        }
      }
      if (!newRunId) {
        throw new Error("Simulation did not appear within 30 seconds");
      }

      // Apply labels and note if provided.
      if (labels.length > 0) {
        await api.PUT("/api/runs/{scenario}/{run_dir_name}/labels", {
          params: { path: splitRunId(newRunId) },
          body: { labels },
        });
      }
      if (note.trim()) {
        await api.PUT("/api/runs/{scenario}/{run_dir_name}/note", {
          params: { path: splitRunId(newRunId) },
          body: { content: note.trim() },
        });
      }

      return newRunId;
    },
    onSuccess: runId => {
      router.push(`/runs/${runId}`);
    },
  });

  const phaseBuilderErrors = useMemo(() => validatePhaseBuilder(phaseBuilder), [phaseBuilder]);

  const canSubmit = (() => {
    if (!scenario || !model || !provider) {
      return false;
    }
    if (phaseBuilderErrors.length > 0) {
      return false;
    }
    if (isVeyru) {
      return veyruState !== null && veyruErrors.length === 0;
    }
    return !needsKnobs || !!knobs;
  })();

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
    setVeyruState(null);
    setModelOverrides({});
    setPhaseBuilder(emptyPhaseBuilderState());
  }

  function handleKnobsFileChange(value: string) {
    setKnobsFile(value);
    if (!value) {
      setKnobs(null);
      setModelOverrides({});
      return;
    }
    const cached = queryClient.getQueryData<{ knobs: KnobsMap }>(["knobs", scenario, value]);
    if (cached) {
      setKnobs({ ...cached.knobs });
    } else {
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

      <ModelPicker
        label="Model"
        models={data?.models ?? []}
        selectedModel={model}
        onSelect={handleModelSelect}
      />

      {isVeyru ? (
        <VeyruKnobsForm
          state={veyruState}
          models={data?.models ?? []}
          errors={veyruErrors}
          onChange={setVeyruState}
        />
      ) : (
        <div className="space-y-2">
          <label htmlFor="knobs" className="block text-sm font-medium">
            Knobs
          </label>
          {needsKnobs ? (
            <select
              id="knobs"
              value={knobsFile}
              onChange={e => handleKnobsFileChange(e.target.value)}
              disabled={!hasSelectedModel}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm disabled:bg-muted disabled:text-muted-foreground"
            >
              <option value="">
                {hasSelectedModel ? "Select a knobs preset..." : "Select a model first..."}
              </option>
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
      )}

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

      {agentRoles.length > 0 ? (
        <div className="space-y-2">
          <label className="block text-sm font-medium">Phases</label>
          <p className="text-xs text-muted-foreground">
            Optionally script mid-run agent swaps. Each phase fires at its boundary round; total
            round_count is the sum of all phase durations.
          </p>
          <PhaseBuilder
            state={phaseBuilder}
            onChange={setPhaseBuilder}
            agents={agentRoles}
            models={data?.models ?? []}
            scenarioHasPostmortem={agentRoles.some(a => a.channels.includes("postmortem"))}
          />
          {phaseBuilderErrors.length > 0 ? (
            <ul className="list-disc space-y-0.5 pl-4 text-xs text-destructive">
              {phaseBuilderErrors.map((err, i) => (
                <li key={i}>{err}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <div className="space-y-2">
        <label className="block text-sm font-medium">Labels</label>
        <p className="text-xs text-muted-foreground">Tag this run for easy filtering later.</p>
        {labels.length > 0 ? (
          <div className="flex flex-wrap gap-1.5 pb-1">
            {labels.map(label => {
              const color = labelColor(label);
              return (
                <span
                  key={label}
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${color.bg} ${color.text}`}
                >
                  {label}
                  <button
                    type="button"
                    onClick={() => setLabels(labels.filter(l => l !== label))}
                    className="rounded-full p-0.5 transition-colors hover:bg-black/10 dark:hover:bg-white/10"
                  >
                    <X className="h-2.5 w-2.5" />
                  </button>
                </span>
              );
            })}
          </div>
        ) : null}
        <div className="flex flex-wrap gap-1.5">
          <input
            type="text"
            className="w-48 rounded-md border border-input bg-background px-2 py-1 text-xs placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            placeholder="Type a label and press Enter..."
            value={labelInput}
            onChange={e => setLabelInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter") {
                e.preventDefault();
                const trimmed = labelInput.trim().toLowerCase();
                if (trimmed && !labels.includes(trimmed)) {
                  setLabels([...labels, trimmed].sort());
                }
                setLabelInput("");
              }
            }}
          />
          {(allLabelsQuery.data?.labels ?? [])
            .filter(l => !labels.includes(l))
            .map(suggestion => {
              const color = labelColor(suggestion);
              return (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => setLabels([...labels, suggestion].sort())}
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium opacity-50 transition-opacity hover:opacity-100 ${color.bg} ${color.text}`}
                >
                  + {suggestion}
                </button>
              );
            })}
        </div>
      </div>

      <div className="space-y-2">
        <label htmlFor="run-note" className="block text-sm font-medium">
          Note
        </label>
        <p className="text-xs text-muted-foreground">
          Describe what you changed or what you expect from this run.
        </p>
        <textarea
          id="run-note"
          className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs leading-relaxed placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          rows={4}
          value={note}
          onChange={e => setNote(e.target.value)}
          placeholder="e.g. veyru-v4: reduced epoch budgets to [1.0, 0.6, 0.3, 0.2], added code invention hints..."
        />
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
