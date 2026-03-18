"use client";

import { useState } from "react";
import { X } from "lucide-react";
import Markdown from "react-markdown";
import { cn } from "@/shared/lib/cn";
import { deriveInitials, type AgentColor } from "./agent-colors";

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

type DrawerTab = "prompt" | "messages";

interface Agent {
  agent_id: string;
  role_name: string;

  system_prompt: string;
}

interface Message {
  message_id: string;
  channel_id: string;
  sender_agent_id: string;
  text: string;
  timestamp: string;
  turn_number: number;
  round_number: number;
}

interface AgentDrawerProps {
  agent: Agent;
  messages: Message[];
  agentColor: AgentColor;
  channelColorMap: Map<string, { bg: string; fg: string }>;
  onClose: () => void;
}

export function AgentDrawer({
  agent,
  messages,
  agentColor,
  channelColorMap,
  onClose,
}: AgentDrawerProps) {
  const [activeTab, setActiveTab] = useState<DrawerTab>("prompt");
  const agentMessages = messages.filter(m => m.sender_agent_id === agent.agent_id);

  return (
    <div className="absolute inset-y-0 right-0 z-10 flex w-[calc(100%-192px)] flex-col border-l border-border bg-background">
      {/* Header */}
      <div className="flex flex-shrink-0 items-center gap-3 border-b border-border px-5 py-3">
        <div
          className={cn(
            "flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg text-xs font-semibold",
            agentColor.bg,
            agentColor.fg
          )}
        >
          {deriveInitials(agent.role_name)}
        </div>
        <div>
          <div className="text-[15px] font-medium">{agent.role_name}</div>
        </div>
        <button
          className="ml-auto rounded p-1 text-muted-foreground transition-colors hover:bg-muted"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex flex-shrink-0 border-b border-border px-5">
        <button
          className={cn(
            "-mb-px border-b-2 px-3 py-2 text-xs transition-colors",
            activeTab === "prompt"
              ? "border-foreground text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
          onClick={() => setActiveTab("prompt")}
        >
          System prompt
        </button>
        <button
          className={cn(
            "-mb-px border-b-2 px-3 py-2 text-xs transition-colors",
            activeTab === "messages"
              ? "border-foreground text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
          onClick={() => setActiveTab("messages")}
        >
          Messages ({agentMessages.length})
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === "prompt" ? (
          <div className="p-5">
            <div className="rounded-lg bg-muted/50 p-3 text-xs leading-relaxed text-muted-foreground whitespace-pre-wrap">
              {agent.system_prompt}
            </div>
          </div>
        ) : (
          <div className="py-2">
            {agentMessages.map(msg => {
              const chColor = channelColorMap.get(msg.channel_id);
              return (
                <div key={msg.message_id} className="flex gap-2.5 px-5 py-2">
                  <div className="flex w-5 shrink-0 flex-col items-center justify-center">
                    <span className="text-[10px] font-medium leading-none text-muted-foreground/50">
                      {msg.turn_number}
                    </span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex items-baseline gap-1.5">
                      <span
                        className={cn(
                          "rounded-full px-1.5 py-px text-[10px] font-medium leading-relaxed",
                          chColor?.bg,
                          chColor?.fg
                        )}
                      >
                        #{msg.channel_id}
                      </span>
                      <span className="text-[10px] text-muted-foreground">
                        {formatTime(msg.timestamp)}
                      </span>
                    </div>
                    <div className="prose prose-xs max-w-none text-xs leading-relaxed text-muted-foreground [&_strong]:text-foreground [&_ul]:ml-4 [&_ul]:list-disc [&_ol]:ml-4 [&_ol]:list-decimal [&_p]:my-1 [&_li]:my-0.5">
                      <Markdown>{msg.text}</Markdown>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
