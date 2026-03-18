"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Loader2, XCircle } from "lucide-react";
import Link from "next/link";
import { api } from "@/shared/lib/api-client";
import { buildAgentColorMap, buildChannelColorMap } from "./agent-colors";
import { AgentDrawer } from "./agent-drawer";
import { ChatPane } from "./chat-pane";
import { RunSidebar } from "./run-sidebar";

function humanizeSnakeCase(value: string): string {
  return value
    .split("_")
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function RunDetail({ runId }: { runId: string }) {
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

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

  const agentColorMap = buildAgentColorMap(data.agents.map(a => a.agent_id));
  const channelColorMap = buildChannelColorMap(data.channel_ids);
  const maxRound = Math.max(...data.messages.map(m => m.round_number), 0);
  const agentModel = data.agents[0]?.model ?? "unknown";

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
        <h1 className="text-base font-medium">{humanizeSnakeCase(data.scenario_name)}</h1>
        <span className="text-[13px] text-muted-foreground">
          {maxRound} rounds · {data.total_turns} turns · {data.agents.length} agents · {agentModel}
        </span>
      </div>

      {/* Shell */}
      <div className="relative grid h-[calc(100vh-120px)] min-h-[500px] grid-cols-[192px_1fr] overflow-hidden rounded-xl border border-border bg-background">
        <RunSidebar
          channelIds={data.channel_ids}
          agents={data.agents}
          selectedChannel={selectedChannel}
          selectedAgent={selectedAgent}
          agentColorMap={agentColorMap}
          onSelectChannel={ch => {
            setSelectedChannel(ch);
            setSelectedAgent(null);
          }}
          onSelectAgent={agentId => {
            setSelectedAgent(agentId);
          }}
        />
        <ChatPane
          messages={data.messages}
          agents={data.agents}
          channelIds={data.channel_ids}
          selectedChannel={selectedChannel}
          agentColorMap={agentColorMap}
          channelColorMap={channelColorMap}
          onSelectAgent={setSelectedAgent}
        />

        {/* Agent drawer */}
        {activeAgent && activeAgentColor ? (
          <AgentDrawer
            agent={activeAgent}
            messages={data.messages}
            agentColor={activeAgentColor}
            channelColorMap={channelColorMap}
            onClose={() => setSelectedAgent(null)}
          />
        ) : null}
      </div>
    </div>
  );
}
