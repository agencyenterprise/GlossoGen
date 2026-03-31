"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, PanelRightClose } from "lucide-react";
import { cn } from "@/shared/lib/cn";
import { deriveInitials, type AgentColor } from "./agent-colors";
import type { components } from "@/types/api.gen";

type AgentDetail = components["schemas"]["AgentDetail"];

interface ReasoningPanelProps {
  agents: AgentDetail[];
  agentColorMap: Map<string, AgentColor>;
  streamingAgentIds: Set<string>;
  partialText: Map<string, string>;
  onClose: () => void;
}

/** A reasoning block that finished streaming. */
interface CompletedEntry {
  id: number;
  agentId: string;
  text: string;
}

const FADE_AFTER_MS = 3000;

let entryCounter = 0;

export function ReasoningPanel({
  agents,
  agentColorMap,
  streamingAgentIds,
  partialText,
  onClose,
}: ReasoningPanelProps) {
  // Track deselected agents — all agents are visible by default,
  // including newly discovered ones (no need to sync on agent list changes).
  const [deselectedAgents, setDeselectedAgents] = useState<Set<string>>(new Set());
  const [completedEntries, setCompletedEntries] = useState<CompletedEntry[]>([]);
  // IDs of entries currently fading (between 0s and FADE_AFTER_MS after completion)
  const [fadingIds, setFadingIds] = useState<Set<number>>(new Set());
  const prevStreamingRef = useRef<Set<string>>(new Set());
  const lastTextRef = useRef<Map<string, string>>(new Map());
  const scrollRef = useRef<HTMLDivElement>(null);

  // Snapshot partial text while it's still available (before is_final clears it)
  for (const [agentId, text] of partialText) {
    if (text) {
      lastTextRef.current.set(agentId, text);
    }
  }

  // Detect when an agent stops streaming -> move to completed entries
  useEffect(() => {
    const prev = prevStreamingRef.current;
    for (const agentId of prev) {
      if (!streamingAgentIds.has(agentId)) {
        const text = lastTextRef.current.get(agentId);
        lastTextRef.current.delete(agentId);
        if (text) {
          const id = ++entryCounter;
          setCompletedEntries(entries => [...entries, { id, agentId, text }]);
          setFadingIds(ids => new Set(ids).add(id));

          // After FADE_AFTER_MS: start CSS fade-out, then remove the entry
          setTimeout(() => {
            setFadingIds(ids => {
              const next = new Set(ids);
              next.delete(id);
              return next;
            });
            // Remove the entry after the CSS transition completes (500ms)
            setTimeout(() => {
              setCompletedEntries(prev => prev.filter(e => e.id !== id));
            }, 500);
          }, FADE_AFTER_MS);
        }
      }
    }
    prevStreamingRef.current = new Set(streamingAgentIds);
  }, [streamingAgentIds, partialText]);

  // Keep the newest content visible. When entries are removed from the
  // top, scrollTop can exceed the new scrollHeight, leaving empty space.
  // Clamping scrollTop after every change prevents this.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const maxScroll = el.scrollHeight - el.clientHeight;
    if (el.scrollTop > maxScroll) {
      el.scrollTop = maxScroll;
    } else if (maxScroll - el.scrollTop < 100) {
      el.scrollTop = maxScroll;
    }
  });

  const isAgentSelected = (agentId: string) => !deselectedAgents.has(agentId);

  const toggleAgent = (agentId: string) => {
    setDeselectedAgents(prev => {
      const next = new Set(prev);
      if (next.has(agentId)) {
        next.delete(agentId);
      } else {
        next.add(agentId);
      }
      return next;
    });
  };

  const agentMap = new Map(agents.map(a => [a.agent_id, a]));

  // Active streaming entries
  const activeEntries = [...streamingAgentIds]
    .filter(id => isAgentSelected(id))
    .map(id => ({
      agentId: id,
      text: partialText.get(id) ?? "",
      isCompleted: false,
    }));

  const visibleCompleted = completedEntries
    .filter(e => isAgentSelected(e.agentId))
    .map(e => ({
      ...e,
      state: fadingIds.has(e.id) ? ("highlighted" as const) : ("settled" as const),
    }));

  return (
    <div className="flex flex-col overflow-hidden border-l border-border">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-border px-3.5 py-2.5">
        <span className="text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">
          Live Reasoning
        </span>
        <button
          className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          onClick={onClose}
          title="Hide reasoning panel"
        >
          <PanelRightClose className="h-4 w-4" />
        </button>
      </div>

      {/* Agent filter dropdown */}
      <AgentFilterDropdown
        agents={agents}
        agentColorMap={agentColorMap}
        streamingAgentIds={streamingAgentIds}
        isAgentSelected={isAgentSelected}
        onToggle={toggleAgent}
        onSelectAll={() => setDeselectedAgents(new Set())}
        onDeselectAll={() => setDeselectedAgents(new Set(agents.map(a => a.agent_id)))}
      />

      {/* Reasoning entries */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3.5 py-2">
        {activeEntries.length === 0 && visibleCompleted.length === 0 ? (
          <p className="py-8 text-center text-[11px] text-muted-foreground">
            Waiting for agents to start reasoning...
          </p>
        ) : (
          <div className="flex flex-col gap-2.5">
            {visibleCompleted.map(entry => (
              <ReasoningCard
                key={`completed-${entry.id}`}
                agentId={entry.agentId}
                text={entry.text}
                agent={agentMap.get(entry.agentId)}
                color={agentColorMap.get(entry.agentId)}
                state={entry.state}
              />
            ))}
            {activeEntries.map(entry => (
              <ReasoningCard
                key={`active-${entry.agentId}`}
                agentId={entry.agentId}
                text={entry.text}
                agent={agentMap.get(entry.agentId)}
                color={agentColorMap.get(entry.agentId)}
                state="streaming"
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ReasoningCard({
  agentId,
  text,
  agent,
  color,
  state,
}: {
  agentId: string;
  text: string;
  agent: AgentDetail | undefined;
  color: AgentColor | undefined;
  state: "streaming" | "highlighted" | "settled";
}) {
  return (
    <div
      className={cn(
        "rounded-lg border px-2.5 py-2 transition-all",
        state === "settled" ? "duration-500" : "duration-300",
        state === "streaming" && "border-border bg-background",
        state === "highlighted" && "border-green-200 bg-green-50/50",
        state === "settled" && "border-transparent opacity-0"
      )}
    >
      {/* Agent badge */}
      <div className="mb-1 flex items-center gap-1.5">
        <div
          className={cn(
            "flex h-4 w-4 shrink-0 items-center justify-center rounded text-[7px] font-semibold",
            color?.bg ?? "bg-gray-100",
            color?.fg ?? "text-gray-800"
          )}
        >
          {deriveInitials(agent?.role_name ?? agentId)}
        </div>
        <span className="text-[10px] font-medium text-muted-foreground">
          {agent?.role_name ?? agentId}
        </span>
        {state === "streaming" ? (
          <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-green-500" />
        ) : null}
      </div>

      {/* Reasoning text */}
      <p className="whitespace-pre-wrap text-[11px] leading-relaxed text-foreground/80">
        {text || "..."}
      </p>
    </div>
  );
}

function AgentFilterDropdown({
  agents,
  agentColorMap,
  streamingAgentIds,
  isAgentSelected,
  onToggle,
  onSelectAll,
  onDeselectAll,
}: {
  agents: AgentDetail[];
  agentColorMap: Map<string, AgentColor>;
  streamingAgentIds: Set<string>;
  isAgentSelected: (id: string) => boolean;
  onToggle: (id: string) => void;
  onSelectAll: () => void;
  onDeselectAll: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const selectedCount = agents.filter(a => isAgentSelected(a.agent_id)).length;
  const label =
    selectedCount === agents.length
      ? "All agents"
      : selectedCount === 0
        ? "No agents"
        : `${selectedCount} of ${agents.length}`;

  return (
    <div ref={ref} className="relative shrink-0 border-b border-border px-3.5 py-2">
      <button
        className="flex w-full items-center justify-between rounded-md border border-border bg-background px-2.5 py-1.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted"
        onClick={() => setOpen(prev => !prev)}
      >
        <span>{label}</span>
        <ChevronDown className={cn("h-3 w-3 transition-transform", open && "rotate-180")} />
      </button>

      {open ? (
        <div className="absolute left-2 right-2 z-20 mt-1 rounded-md border border-border bg-background py-1 shadow-lg">
          {/* Select all / Deselect all */}
          <div className="flex gap-2 border-b border-border px-2.5 py-1.5">
            <button
              className="text-[10px] font-medium text-foreground/70 hover:text-foreground"
              onClick={onSelectAll}
            >
              Select all
            </button>
            <span className="text-[10px] text-muted-foreground/50">|</span>
            <button
              className="text-[10px] font-medium text-foreground/70 hover:text-foreground"
              onClick={onDeselectAll}
            >
              Deselect all
            </button>
          </div>

          {/* Agent list */}
          {agents.map(agent => {
            const color = agentColorMap.get(agent.agent_id);
            const selected = isAgentSelected(agent.agent_id);
            const streaming = streamingAgentIds.has(agent.agent_id);
            return (
              <label
                key={agent.agent_id}
                className="flex cursor-pointer items-center gap-2 px-2.5 py-1.5 transition-colors hover:bg-muted"
              >
                <input
                  type="checkbox"
                  checked={selected}
                  onChange={() => onToggle(agent.agent_id)}
                  className="h-3 w-3 rounded border-border accent-foreground"
                />
                <div
                  className={cn(
                    "flex h-4 w-4 shrink-0 items-center justify-center rounded text-[7px] font-semibold",
                    color?.bg ?? "bg-gray-100",
                    color?.fg ?? "text-gray-800"
                  )}
                >
                  {deriveInitials(agent.role_name)}
                </div>
                <span className="flex-1 text-[11px] text-foreground">{agent.role_name}</span>
                {streaming ? (
                  <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-green-500" />
                ) : null}
              </label>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
