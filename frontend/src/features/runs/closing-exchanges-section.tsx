"use client";

import { AlertTriangle, MessageCircleQuestion } from "lucide-react";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { deriveInitials, type AgentColor } from "./agent-colors";
import { formatTime } from "./format";
import { ProseMarkdown } from "./prose-markdown";

type AgentDetail = components["schemas"]["AgentDetail"];
type ClosingExchangeEntry = components["schemas"]["ClosingExchangeEntry"];

interface ClosingExchangesSectionProps {
  exchanges: ClosingExchangeEntry[];
  agentMap: Map<string, AgentDetail>;
  agentColorMap: Map<string, AgentColor>;
  onSelectAgent: (agentId: string) => void;
}

/** The closing prompt each agent was sent once the run completed, and what it
 *  answered. Rendered after the last round of "all activity". The prompt is
 *  shown once when every agent was sent the same text, and above each answer
 *  otherwise. */
export function ClosingExchangesSection({
  exchanges,
  agentMap,
  agentColorMap,
  onSelectAgent,
}: ClosingExchangesSectionProps) {
  const sharedPrompt =
    new Set(exchanges.map(e => e.prompt)).size === 1 ? exchanges[0]!.prompt : null;
  return (
    <section className="px-4 pb-4 pt-3.5">
      <div className="flex items-center gap-2.5 pb-2">
        <div className="h-px flex-1 bg-border" />
        <span className="whitespace-nowrap text-[11px] text-muted-foreground">After the run</span>
        <div className="h-px flex-1 bg-border" />
      </div>
      {sharedPrompt !== null ? <ClosingPrompt text={sharedPrompt} /> : null}
      <div className="space-y-3">
        {exchanges.map(exchange => (
          <ClosingExchangeCard
            key={exchange.message_id}
            exchange={exchange}
            agent={agentMap.get(exchange.agent_id)}
            color={agentColorMap.get(exchange.agent_id)}
            showPrompt={sharedPrompt === null}
            onSelectAgent={onSelectAgent}
          />
        ))}
      </div>
    </section>
  );
}

function ClosingPrompt({ text }: { text: string }) {
  return (
    <div className="mb-3 rounded-md border border-border/60 bg-muted/35 px-3 py-2 dark:bg-muted/20">
      <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
        <MessageCircleQuestion className="h-3 w-3 shrink-0" />
        Closing prompt
      </div>
      <ProseMarkdown>{text}</ProseMarkdown>
    </div>
  );
}

interface ClosingExchangeCardProps {
  exchange: ClosingExchangeEntry;
  agent: AgentDetail | undefined;
  color: AgentColor | undefined;
  showPrompt: boolean;
  onSelectAgent: (agentId: string) => void;
}

function ClosingExchangeCard({
  exchange,
  agent,
  color,
  showPrompt,
  onSelectAgent,
}: ClosingExchangeCardProps) {
  const name = agent?.role_name ?? exchange.agent_id;
  return (
    <div className="flex gap-2.5">
      <button
        aria-label={`Open agent ${name}`}
        className={cn(
          "flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-md text-[10px] font-semibold transition-opacity hover:opacity-75",
          color?.bg,
          color?.fg
        )}
        onClick={() => onSelectAgent(exchange.agent_id)}
      >
        {deriveInitials(name)}
      </button>
      <div className="min-w-0 flex-1 pr-4">
        <div className="mb-0.5 flex flex-wrap items-baseline gap-1.5">
          <button
            className="text-[13px] font-medium hover:underline"
            onClick={() => onSelectAgent(exchange.agent_id)}
          >
            {name}
          </button>
          <span className="text-[10px] text-muted-foreground">{exchange.model}</span>
          <span className="text-[10px] text-muted-foreground">
            {formatTime(exchange.timestamp)}
          </span>
        </div>
        {showPrompt ? <ClosingPrompt text={exchange.prompt} /> : null}
        {exchange.status === "answered" ? (
          <ProseMarkdown className="text-foreground">{exchange.answer ?? ""}</ProseMarkdown>
        ) : (
          <div className="flex items-start gap-1.5 rounded border border-red-300/70 bg-red-50/50 px-2 py-1 text-[11px] text-red-700 dark:border-red-800/50 dark:bg-red-950/20 dark:text-red-300">
            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
            <span className="break-words">No answer: {exchange.failure}</span>
          </div>
        )}
      </div>
    </div>
  );
}
