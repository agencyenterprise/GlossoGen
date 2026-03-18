"use client";

import { useCallback, useMemo, useState } from "react";
import { flushSync } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, HelpCircle, Loader2, XCircle } from "lucide-react";
import Link from "next/link";
import { api } from "@/shared/lib/api-client";
import { cn } from "@/shared/lib/cn";
import { buildAgentColorMap, buildChannelColorMap } from "./agent-colors";
import { AgentDrawer } from "./agent-drawer";
import { ChatPane } from "./chat-pane";
import { EvalPanel } from "./eval-panel";
import { humanize } from "./format";
import { RunSidebar } from "./run-sidebar";
import { ScenarioDescriptionModal } from "./scenario-description-modal";

export function RunDetail({ runId }: { runId: string }) {
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [highlightedMessageId, setHighlightedMessageId] = useState<string | null>(null);
  const [highlightNonce, setHighlightNonce] = useState(0);
  const [showDescription, setShowDescription] = useState(false);

  const handleSelectChannel = useCallback((ch: string | null) => {
    setSelectedChannel(ch);
    setSelectedAgent(null);
  }, []);

  function handleNavigateToMessage(messageId: string, channelId: string) {
    flushSync(() => {
      setSelectedAgent(null);
      setSelectedChannel(channelId);
      setHighlightedMessageId(null);
    });
    setHighlightNonce(n => n + 1);
    setHighlightedMessageId(messageId);
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ["run", runId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/runs/{run_id}", {
        params: { path: { run_id: runId } },
      });
      if (error) {
        throw new Error("Failed to fetch run detail");
      }
      return data;
    },
  });

  const agentColorMap = useMemo(
    () => (data ? buildAgentColorMap(data.agents.map(a => a.agent_id)) : new Map()),
    [data]
  );
  const channelColorMap = useMemo(
    () => (data ? buildChannelColorMap(data.channel_ids) : new Map()),
    [data]
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-20 text-destructive">
        <XCircle className="h-8 w-8" />
        <p>Failed to load run</p>
      </div>
    );
  }

  const maxRound = data.messages.reduce((max, m) => Math.max(max, m.round_number), 0);
  const uniqueModels = [...new Set(data.agents.map(a => a.model))];
  const modelLabel =
    uniqueModels.length === 1
      ? uniqueModels[0]
      : uniqueModels.length === 0
        ? "unknown"
        : `${uniqueModels.length} models`;

  const evaluation = data.evaluation;
  const activeAgent = data.agents.find(a => a.agent_id === selectedAgent);
  const activeAgentColor = selectedAgent ? agentColorMap.get(selectedAgent) : undefined;

  return (
    <div className="mx-auto max-w-7xl px-4 py-4">
      {/* Back link */}
      <Link
        href="/runs"
        className="mb-2 inline-flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> back to runs
      </Link>

      {/* Header */}
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <span className="flex items-center gap-1.5">
          <h1 className="text-base font-medium">{humanize(data.scenario_name)}</h1>
          <button
            aria-label="Scenario description"
            className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={() => setShowDescription(true)}
          >
            <HelpCircle className="h-4 w-4" />
          </button>
        </span>
        <span className="text-[13px] text-muted-foreground">
          {maxRound} rounds · {data.total_turns} turns · {data.agents.length} agents ·{" "}
          {uniqueModels.length <= 1 ? (
            modelLabel
          ) : (
            <span className="group relative cursor-default">
              {modelLabel}
              <span className="pointer-events-none absolute right-0 top-full z-20 mt-1 hidden w-max rounded-md border border-border bg-background px-3 py-2 text-xs shadow-lg group-hover:block">
                {data.agents.map(a => (
                  <div key={a.agent_id} className="flex justify-between gap-4 py-0.5">
                    <span className="text-muted-foreground">{humanize(a.agent_id)}</span>
                    <span className="font-mono">{a.model}</span>
                  </div>
                ))}
              </span>
            </span>
          )}
        </span>
      </div>

      {showDescription ? (
        <ScenarioDescriptionModal
          scenarioName={humanize(data.scenario_name)}
          description={data.scenario_description}
          onClose={() => setShowDescription(false)}
        />
      ) : null}

      {/* Shell */}
      <div
        className={cn(
          "relative grid h-[calc(100vh-120px)] min-h-[500px] overflow-hidden rounded-xl border border-border bg-background",
          evaluation !== null ? "grid-cols-[192px_1fr_280px]" : "grid-cols-[192px_1fr]"
        )}
      >
        <RunSidebar
          channelIds={data.channel_ids}
          agents={data.agents}
          selectedChannel={selectedChannel}
          selectedAgent={selectedAgent}
          agentColorMap={agentColorMap}
          onSelectChannel={handleSelectChannel}
          onSelectAgent={setSelectedAgent}
        />
        <ChatPane
          messages={data.messages}
          agents={data.agents}
          selectedChannel={selectedChannel}
          agentColorMap={agentColorMap}
          channelColorMap={channelColorMap}
          onSelectAgent={setSelectedAgent}
          highlightedMessageId={highlightedMessageId}
          highlightNonce={highlightNonce}
        />

        {/* Eval panel */}
        {evaluation !== null ? <EvalPanel evaluation={evaluation} /> : null}

        {/* Agent drawer */}
        {activeAgent && activeAgentColor ? (
          <AgentDrawer
            agent={activeAgent}
            messages={data.messages}
            agentColor={activeAgentColor}
            channelColorMap={channelColorMap}
            onClose={() => setSelectedAgent(null)}
            onNavigateToMessage={handleNavigateToMessage}
            onNavigateToChannel={channelId => {
              setSelectedAgent(null);
              setSelectedChannel(channelId);
            }}
            evalMetrics={data.evaluation?.metrics ?? null}
          />
        ) : null}
      </div>
    </div>
  );
}
