"use client";

import { Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import { ModelPicker } from "./model-picker";
import { getScenarioPlugin } from "./scenario-registry";

interface SourceAgent {
  agent_id: string;
  role_name: string;
  model: string;
  provider: string;
  channel_ids: string[];
}

interface ConfirmArgs {
  sourceBRunId: string;
  replacedAgentId: string;
  sourceBRoundEnd: number;
  roundsAfterSwap: number;
  channelsWithVisibleHistory: string[];
  model: string | null;
  provider: string | null;
  knobs: Record<string, unknown> | null;
}

interface Props {
  isPending: boolean;
  isSuccess: boolean;
  errorMessage: string | null;
  roundStart: number;
  scenarioName: string;
  sourceRoundCount: number | null;
  sourceAgents: SourceAgent[];
  currentRunId: string;
  onConfirm: (args: ConfirmArgs) => void;
  onCancel: () => void;
}

export function CrossRunReplaceAgentModal({
  isPending,
  isSuccess,
  errorMessage,
  roundStart,
  scenarioName,
  sourceRoundCount,
  sourceAgents,
  currentRunId,
  onConfirm,
  onCancel,
}: Props) {
  const defaultAgent = sourceAgents[0];
  const [replacedAgentId, setReplacedAgentId] = useState(defaultAgent?.agent_id ?? "");
  const [sourceBRunId, setSourceBRunId] = useState<string>("");
  const [sourceBFilter, setSourceBFilter] = useState<string>("");
  const [sourceBRoundEnd, setSourceBRoundEnd] = useState<number>(Math.max(1, roundStart - 1));
  const [overrideModel, setOverrideModel] = useState<boolean>(false);
  const [model, setModel] = useState<string>(defaultAgent?.model ?? "");
  const [provider, setProvider] = useState<string>(defaultAgent?.provider ?? "");

  const defaultRoundsAfterSwap =
    sourceRoundCount !== null ? Math.max(1, sourceRoundCount - roundStart) : 1;
  const [roundsAfterSwap, setRoundsAfterSwap] = useState<number>(defaultRoundsAfterSwap);

  const plugin = getScenarioPlugin(scenarioName);

  const { data: candidateRuns, isLoading: candidatesLoading } = useQuery({
    queryKey: ["cross-run-candidates", scenarioName, replacedAgentId],
    enabled: replacedAgentId !== "",
    queryFn: async () => {
      const { data, error } = await api.GET("/api/runs", {
        params: {
          query: {
            scenario: scenarioName,
            contains_agent_id: replacedAgentId,
            status: "scenario_complete",
          },
        },
      });
      if (error) {
        throw new Error("Failed to fetch candidate runs");
      }
      return data;
    },
  });

  const filteredCandidates = useMemo(() => {
    const runs = candidateRuns?.runs ?? [];
    const filter = sourceBFilter.trim().toLowerCase();
    return runs.filter(r => {
      if (r.run_id === currentRunId) return false;
      if (filter === "") return true;
      return r.run_id.toLowerCase().includes(filter);
    });
  }, [candidateRuns, currentRunId, sourceBFilter]);

  const selectedSourceB = useMemo(
    () => candidateRuns?.runs.find(r => r.run_id === sourceBRunId) ?? null,
    [candidateRuns, sourceBRunId]
  );
  const sourceBMaxRound = selectedSourceB?.current_round ?? null;

  // When the user picks (or changes) the source B run, default
  // source_b_round_end to min(roundStart - 1, B_max_round) so the imported
  // agent gets all of B's history without exceeding what B actually played.
  // Adjusted during render per React's "Adjusting state on prop change" pattern.
  const [prevSelectedBRunId, setPrevSelectedBRunId] = useState<string>(sourceBRunId);
  if (prevSelectedBRunId !== sourceBRunId) {
    setPrevSelectedBRunId(sourceBRunId);
    if (sourceBMaxRound !== null) {
      setSourceBRoundEnd(Math.max(1, Math.min(roundStart - 1, sourceBMaxRound)));
    }
  }

  const { data: scenariosData } = useQuery({
    queryKey: ["scenarios"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/scenarios");
      if (error) {
        throw new Error("Failed to fetch scenarios");
      }
      return data;
    },
  });

  function handleAgentChange(nextAgentId: string) {
    setReplacedAgentId(nextAgentId);
    const next = sourceAgents.find(a => a.agent_id === nextAgentId);
    if (next) {
      setModel(next.model);
      setProvider(next.provider);
    }
    setSourceBRunId("");
    setSourceBFilter("");
  }

  function handleModelSelect(selectedModel: string, selectedProvider: string) {
    setModel(selectedModel);
    setProvider(selectedProvider);
  }

  const currentAgent = sourceAgents.find(a => a.agent_id === replacedAgentId);

  function handleConfirmClick() {
    const visibleChannels = currentAgent?.channel_ids ?? [];
    const defaults = plugin.defaultReplaceAgentKnobs;
    const knobs: Record<string, unknown> | null =
      Object.keys(defaults).length > 0 ? { ...defaults } : null;
    onConfirm({
      sourceBRunId,
      replacedAgentId,
      sourceBRoundEnd,
      roundsAfterSwap,
      channelsWithVisibleHistory: visibleChannels,
      model: overrideModel ? model : null,
      provider: overrideModel ? provider : null,
      knobs,
    });
  }

  const canSubmit =
    !isPending &&
    !isSuccess &&
    replacedAgentId !== "" &&
    sourceBRunId !== "" &&
    sourceBRoundEnd >= 1;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/40 px-4 py-4">
      <div className="flex min-h-full items-center justify-center">
        <div className="flex w-full max-w-md max-h-[calc(100vh-2rem)] flex-col overflow-hidden rounded-xl border border-border bg-background shadow-xl">
          <div className="min-h-0 flex-1 overflow-y-auto p-5">
            <h3 className="mb-3 text-sm font-medium">
              Cross-run replace at start of round {roundStart}
            </h3>
            <p className="mb-3 text-xs text-muted-foreground">
              Import an agent from a different completed run (source B) and drop it into this run at
              round {roundStart}, retaining its full pydantic-ai history (text, thinking, tool
              calls) up to the chosen end round of source B. Other agents continue from this run.
            </p>

            <div className="mb-4 space-y-1">
              <label className="block text-sm font-medium">Agent slot to replace</label>
              <select
                className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
                value={replacedAgentId}
                onChange={e => handleAgentChange(e.target.value)}
                disabled={isPending}
              >
                {sourceAgents.map(agent => (
                  <option key={agent.agent_id} value={agent.agent_id}>
                    {agent.agent_id} — {agent.role_name}
                  </option>
                ))}
              </select>
            </div>

            <div className="mb-4 space-y-1">
              <label className="block text-sm font-medium" htmlFor="source-b-run">
                Source B run
              </label>
              <p className="text-[11px] text-muted-foreground">
                Pick a completed run of the same scenario that contains{" "}
                <code className="rounded bg-muted px-1">{replacedAgentId || "the agent"}</code>.
              </p>
              <input
                type="text"
                placeholder="Filter run_id (e.g. 1777977676)"
                className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
                value={sourceBFilter}
                onChange={e => {
                  setSourceBFilter(e.target.value);
                  if (
                    sourceBRunId !== "" &&
                    !sourceBRunId.toLowerCase().includes(e.target.value.trim().toLowerCase())
                  ) {
                    setSourceBRunId("");
                  }
                }}
                disabled={isPending || candidatesLoading || replacedAgentId === ""}
              />
              <select
                id="source-b-run"
                className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
                value={sourceBRunId}
                onChange={e => {
                  const nextId = e.target.value;
                  setSourceBRunId(nextId);
                  const next = candidateRuns?.runs.find(r => r.run_id === nextId);
                  if (next) {
                    setSourceBRoundEnd(Math.min(Math.max(1, roundStart - 1), next.current_round));
                  }
                }}
                disabled={isPending || candidatesLoading || replacedAgentId === ""}
                size={Math.min(8, Math.max(2, filteredCandidates.length + 1))}
              >
                <option value="">— select a source B run —</option>
                {filteredCandidates.map(r => (
                  <option key={r.run_id} value={r.run_id}>
                    {r.run_id} (rounds: {r.current_round})
                  </option>
                ))}
              </select>
              {!candidatesLoading && replacedAgentId !== "" && filteredCandidates.length === 0 ? (
                <p className="text-[11px] text-muted-foreground">No matching runs.</p>
              ) : null}
            </div>

            <div className="mb-4 space-y-1">
              <label className="block text-sm font-medium" htmlFor="source-b-round-end">
                Source B round end
              </label>
              <p className="text-[11px] text-muted-foreground">
                Last round of source B whose events feed into the imported agent&apos;s history.
                Defaults to min(round_start − 1, source B&apos;s round count)
                {sourceBMaxRound !== null
                  ? ` — source B has ${sourceBMaxRound} round${sourceBMaxRound === 1 ? "" : "s"}`
                  : ""}
                .
              </p>
              <input
                id="source-b-round-end"
                type="number"
                min={1}
                max={sourceBMaxRound ?? undefined}
                className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
                value={sourceBRoundEnd}
                onChange={e => {
                  const raw = Math.max(1, Number(e.target.value) || 1);
                  const cap = sourceBMaxRound ?? raw;
                  setSourceBRoundEnd(Math.min(raw, cap));
                }}
                disabled={isPending}
              />
            </div>

            <div className="mb-4 space-y-1">
              <label className="block text-sm font-medium" htmlFor="rounds-after-swap-cross">
                Rounds after replacement
              </label>
              <p className="text-[11px] text-muted-foreground">
                The resumed simulation plays this many rounds following round {roundStart}.
              </p>
              <input
                id="rounds-after-swap-cross"
                type="number"
                min={1}
                className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
                value={roundsAfterSwap}
                onChange={e => setRoundsAfterSwap(Math.max(1, Number(e.target.value) || 1))}
                disabled={isPending}
              />
            </div>

            <div className="mb-4 space-y-1">
              <label className="flex items-center gap-2 text-sm font-medium">
                <input
                  type="checkbox"
                  checked={overrideModel}
                  onChange={e => setOverrideModel(e.target.checked)}
                  disabled={isPending}
                />
                Override imported model
              </label>
              <p className="text-[11px] text-muted-foreground">
                When unchecked, the imported agent runs under the same model/provider it used in
                source B.
              </p>
            </div>

            {overrideModel ? (
              <div className="mb-4">
                <ModelPicker
                  label="Imported model override"
                  models={scenariosData?.models ?? []}
                  selectedModel={model}
                  onSelect={handleModelSelect}
                />
              </div>
            ) : null}

            {isPending ? (
              <div className="mt-4 flex items-start gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-[11px] text-muted-foreground">
                <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin" />
                <div className="space-y-0.5">
                  <p className="font-medium text-foreground">Launching cross-run replace…</p>
                  <p>
                    Cloning source A, copying source B&apos;s history, rewriting the JSONL, and
                    starting the resumed simulation. Usually 10–20 seconds. Redirecting when ready.
                  </p>
                </div>
              </div>
            ) : null}

            {isSuccess ? (
              <div className="mt-4 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-[11px] text-emerald-700 dark:text-emerald-300">
                Launched. Redirecting to the new run…
              </div>
            ) : null}

            {errorMessage !== null ? (
              <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-[11px] text-destructive">
                <p className="font-medium">Cross-run replace failed</p>
                <p className="mt-0.5 wrap-break-word">{errorMessage}</p>
              </div>
            ) : null}
          </div>

          <div className="flex shrink-0 justify-end gap-2 border-t border-border px-5 py-3">
            <button
              className="rounded-md border border-border px-3 py-1 text-[12px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              onClick={onCancel}
              disabled={isPending}
            >
              {errorMessage !== null ? "Close" : "Cancel"}
            </button>
            <button
              className="rounded-md bg-foreground px-3 py-1 text-[12px] font-medium text-background transition-opacity hover:opacity-80 disabled:opacity-50"
              onClick={handleConfirmClick}
              disabled={!canSubmit}
            >
              {isPending
                ? "Launching..."
                : isSuccess
                  ? "Redirecting…"
                  : errorMessage !== null
                    ? "Retry"
                    : "Launch cross-run replace"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
