"use client";

import { useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Loader2, Search, X, XCircle } from "lucide-react";
import Link from "next/link";
import { api } from "@/shared/lib/api-client";
import { cn } from "@/shared/lib/cn";
import { splitRunId } from "@/shared/lib/run-id";
import type { components } from "@/types/api.gen";
import { useGroupPath } from "@/features/auth/group-context";
import { buildAgentColorMap, buildChannelColorMap, deriveInitials } from "../runs/agent-colors";
import { formatTime, humanize } from "../runs/format";
import { type ForkInfo, ForkBranchCard } from "./fork-branch-card";

type ChannelMessage = components["schemas"]["ChannelMessage"];

const TRUNCATE_LENGTH = 120;

interface MessageGroup {
  roundNumber: number;
  messages: ChannelMessage[];
}

function groupMessagesByRound(messages: ChannelMessage[]): MessageGroup[] {
  const groups: MessageGroup[] = [];
  let current: MessageGroup | null = null;

  for (const msg of messages) {
    if (!current || current.roundNumber !== msg.round_number) {
      current = { roundNumber: msg.round_number, messages: [] };
      groups.push(current);
    }
    current.messages.push(msg);
  }

  return groups;
}

export function BranchesTimeline({ runId }: { runId: string }) {
  const groupPath = useGroupPath();
  const [expandedMessages, setExpandedMessages] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");

  const toggleExpanded = useCallback((messageId: string) => {
    setExpandedMessages(prev => {
      const next = new Set(prev);
      if (next.has(messageId)) {
        next.delete(messageId);
      } else {
        next.add(messageId);
      }
      return next;
    });
  }, []);

  const {
    data: runDetail,
    isLoading: detailLoading,
    error: detailError,
  } = useQuery({
    queryKey: ["run", runId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/g/{group_slug}/runs/{scenario}/{run_dir_name}", {
        params: { path: splitRunId(runId) },
      });
      if (error) {
        throw new Error("Failed to fetch run detail");
      }
      return data;
    },
  });

  const { data: allRuns } = useQuery({
    queryKey: ["runs"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/g/{group_slug}/runs");
      if (error) {
        throw new Error("Failed to fetch runs");
      }
      return data;
    },
  });

  const forksByMessageId = useMemo(() => {
    const map = new Map<string, ForkInfo[]>();
    if (!allRuns) {
      return map;
    }
    for (const run of allRuns.runs) {
      if (!run.fork_source) {
        continue;
      }
      if (run.fork_source.source_run_id !== runId) {
        continue;
      }
      const info: ForkInfo = {
        runId: run.run_id,
        status: run.status,
        timestamp: run.timestamp,
        models: run.models,
      };
      const targetId = run.fork_source.target_message_id;
      const existing = map.get(targetId);
      if (existing) {
        existing.push(info);
      } else {
        map.set(targetId, [info]);
      }
    }
    return map;
  }, [allRuns, runId]);

  const agentColorMap = useMemo(() => {
    if (!runDetail) {
      return new Map();
    }
    return buildAgentColorMap(runDetail.agents.map(a => a.agent_id));
  }, [runDetail]);

  const agentNameMap = useMemo(() => {
    const map = new Map<string, string>();
    if (!runDetail) {
      return map;
    }
    for (const agent of runDetail.agents) {
      map.set(agent.agent_id, agent.role_name);
    }
    return map;
  }, [runDetail]);

  const channelColorMap = useMemo(() => {
    if (!runDetail) {
      return new Map();
    }
    return buildChannelColorMap(runDetail.channel_ids);
  }, [runDetail]);

  const roundGroups = useMemo(() => {
    if (!runDetail) {
      return [];
    }
    const sorted = [...runDetail.messages].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    return groupMessagesByRound(sorted);
  }, [runDetail]);

  const searchLower = searchQuery.toLowerCase().trim();

  const filteredRoundGroups = useMemo(() => {
    if (searchLower === "") {
      return roundGroups;
    }
    const filtered: MessageGroup[] = [];
    for (const group of roundGroups) {
      const matching = group.messages.filter(msg => {
        const roleName = agentNameMap.get(msg.sender_agent_id) ?? msg.sender_agent_id;
        return (
          msg.text.toLowerCase().includes(searchLower) ||
          roleName.toLowerCase().includes(searchLower) ||
          msg.channel_id.toLowerCase().includes(searchLower)
        );
      });
      if (matching.length > 0) {
        filtered.push({ roundNumber: group.roundNumber, messages: matching });
      }
    }
    return filtered;
  }, [roundGroups, searchLower, agentNameMap]);

  if (detailLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (detailError || !runDetail) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-20 text-destructive">
        <XCircle className="h-8 w-8" />
        <p>Failed to load run</p>
      </div>
    );
  }

  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      {/* Header */}
      <div className="mb-8 flex items-center gap-3">
        <Link
          href={groupPath("/branches")}
          className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{humanize(runDetail.scenario_name)}</h1>
          <p className="text-sm text-muted-foreground">
            {runDetail.agents.length} agents &middot;{" "}
            {forksByMessageId.size > 0
              ? `${Array.from(forksByMessageId.values()).reduce((sum, f) => sum + f.length, 0)} forks`
              : "No forks"}
          </p>
        </div>
      </div>

      {/* Search */}
      <div className="relative mb-6">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search messages…"
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          className="w-full rounded-md border border-border bg-background py-2 pl-9 pr-9 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
        {searchQuery !== "" ? (
          <button
            onClick={() => setSearchQuery("")}
            className="absolute right-3 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        ) : null}
      </div>

      {/* Two-column timeline: messages (left) | trunk | forks (right) */}
      <div className="grid grid-cols-[3fr_24px_1fr]">
        {filteredRoundGroups.map(group => (
          <div key={group.roundNumber} className="contents">
            {/* Round separator */}
            <div className="mb-3 flex items-center justify-end">
              <div className="h-px flex-1 bg-border" />
              <span className="ml-3 shrink-0 text-xs font-medium text-muted-foreground">
                Round {group.roundNumber}
              </span>
            </div>
            <div className="relative mb-3 flex justify-center">
              <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border" />
              <div className="relative z-10 h-3 w-3 rounded-full border-2 border-border bg-background" />
            </div>
            <div className="mb-3 flex items-center">
              <div className="h-px flex-1 bg-border" />
            </div>

            {/* Messages */}
            {group.messages.map(msg => {
              const roleName = agentNameMap.get(msg.sender_agent_id) ?? msg.sender_agent_id;
              const color = agentColorMap.get(msg.sender_agent_id);
              const channelColor = channelColorMap.get(msg.channel_id);
              const isExpanded = expandedMessages.has(msg.message_id);
              const needsTruncation = msg.text.length > TRUNCATE_LENGTH;
              const forks = forksByMessageId.get(msg.message_id);

              return (
                <div key={msg.message_id} className="contents">
                  {/* Left column — message card */}
                  <div className="mb-2 pr-2">
                    <div
                      className={cn(
                        "rounded-md border border-border px-3 py-2 transition-colors",
                        forks ? "border-violet-200 dark:border-violet-800/50" : ""
                      )}
                    >
                      {/* Agent + channel + time */}
                      <div className="mb-1 flex items-center gap-2 text-xs">
                        <span
                          className={cn(
                            "inline-flex h-5 w-5 items-center justify-center rounded-full text-[9px] font-bold",
                            color?.bg ?? "bg-gray-100",
                            color?.fg ?? "text-gray-600"
                          )}
                        >
                          {deriveInitials(roleName)}
                        </span>
                        <span className="font-medium">{humanize(roleName)}</span>
                        <span
                          className={cn(
                            "rounded-full px-1.5 py-0.5 text-[10px] font-medium",
                            channelColor?.bg ?? "bg-gray-50",
                            channelColor?.fg ?? "text-gray-600"
                          )}
                        >
                          #{humanize(msg.channel_id)}
                        </span>
                        <span className="ml-auto text-muted-foreground">
                          {formatTime(msg.timestamp)}
                        </span>
                      </div>

                      {/* Message text */}
                      <button
                        className="w-full text-left text-sm text-foreground/80"
                        onClick={() => {
                          if (needsTruncation) {
                            toggleExpanded(msg.message_id);
                          }
                        }}
                        disabled={!needsTruncation}
                      >
                        {needsTruncation && !isExpanded ? (
                          <span>
                            {msg.text.slice(0, TRUNCATE_LENGTH)}
                            <span className="text-muted-foreground">…</span>
                          </span>
                        ) : (
                          <span className="whitespace-pre-wrap">{msg.text}</span>
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Center column — trunk line + dot */}
                  <div className="relative mb-2 flex justify-center">
                    {/* Continuous vertical line behind the dot */}
                    <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border" />
                    <div
                      className={cn(
                        "relative z-10 mt-2.5 h-2.5 w-2.5 rounded-full",
                        forks ? "bg-violet-500 dark:bg-violet-400" : "bg-border"
                      )}
                    />
                  </div>

                  {/* Right column — fork cards (or empty) */}
                  <div className="mb-2 pl-2">
                    {forks ? (
                      <ForkBranchCard forks={forks} targetMessageId={msg.message_id} />
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        ))}

        {/* End marker */}
        <div className="flex items-center justify-end pt-2">
          <span className="text-xs text-muted-foreground">End of run</span>
        </div>
        <div className="flex justify-center pt-2">
          <div className="h-3 w-3 rounded-full border-2 border-muted-foreground/30 bg-background" />
        </div>
        <div className="pt-2" />
      </div>
    </main>
  );
}
