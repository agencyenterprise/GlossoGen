"use client";

import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import { flushSync } from "react-dom";
import Link from "next/link";
import { ArrowLeft, HelpCircle, Package, PanelRightOpen, Play } from "lucide-react";
import { Tooltip } from "@/shared/components/ui/tooltip";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { GroupProvider } from "@/features/auth/group-context";
import { GuidedTour, type TourStep } from "@/features/onboarding/guided-tour";
import { buildAgentColorMap, buildChannelColorMap } from "./agent-colors";
import { AgentDrawer } from "./agent-drawer";
import { deriveAgentInstances, resolveSelectedInstance } from "./agent-instance";
import { ChatPane } from "./chat-pane";
import { CollapsibleConfigBadges } from "./collapsible-config-badges";
import { ConfigValueModal } from "./config-value-modal";
import { judgeMetadataFromExtras, mergeEntries } from "./display-entry";
import { LabelBadges } from "./eval-label-group";
import { EvalPanel } from "./eval-panel";
import {
  formatConfigValue,
  formatConfigValueFull,
  formatCost,
  formatDayHeader,
  formatDuration,
  humanize,
  sortConfigEntries,
} from "./format";
import { RunSidebar } from "./run-sidebar";
import { getScenarioPlugin } from "./scenario-registry";
import { RoundTimelineModal } from "./round-timeline-modal";
import { ScenarioDescriptionModal } from "./scenario-description-modal";

type RunDetailResponse = components["schemas"]["RunDetailResponse"];

/** The static-asset URL of the baked demo run bundle (see scripts/generate_demo_snapshot.py). */
const DEMO_ZIP_URL = "/demo/run.zip";
/** localStorage key remembering that the visitor already saw the tour. */
const TOUR_SEEN_KEY = "glossogen_demo_tour_seen";
/** The round whose timeline the tour opens to showcase the round panel. */
const TOUR_TIMELINE_ROUND = 1;

/**
 * Read-only run viewer for the public landing-page walkthrough.
 *
 * Composes the real run-viewer child components (sidebar, chat pane, evaluation
 * panel, agent drawer) fed by a frozen ``RunDetailResponse`` loaded from a
 * static asset — no authentication, no SSE, no mutations. Adds a dismissible
 * guided tour that spotlights each interface region.
 */
export function PublicRunViewer({ run }: { run: RunDetailResponse }) {
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [highlightedMessageId, setHighlightedMessageId] = useState<string | null>(null);
  const [highlightNonce, setHighlightNonce] = useState(0);
  const [showDescription, setShowDescription] = useState(false);
  const [showEvalPanel, setShowEvalPanel] = useState(true);
  const [configPreview, setConfigPreview] = useState<{ key: string; value: string } | null>(null);
  const [timelineRound, setTimelineRound] = useState<number | null>(null);
  const [tourOpen, setTourOpen] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return window.localStorage.getItem(TOUR_SEEN_KEY) === null;
  });

  const headerRef = useRef<HTMLDivElement>(null);
  const sidebarRef = useRef<HTMLDivElement>(null);
  const chatRef = useRef<HTMLDivElement>(null);
  const evalRef = useRef<HTMLDivElement>(null);

  const scenarioPlugin = getScenarioPlugin(run.scenario_name);

  const displayEntries = useMemo(() => {
    const judgeMetadataByCallId = judgeMetadataFromExtras(run.scenario_extras);
    const toolMetadataByCallId: Record<string, ReactNode> = {};
    for (const tool of run.tool_use) {
      const node = scenarioPlugin.renderToolMetadata({
        toolName: tool.tool_name,
        callId: tool.call_id,
        extras: run.scenario_extras,
      });
      if (node != null) {
        toolMetadataByCallId[tool.call_id] = node;
      }
    }
    return mergeEntries(
      run.messages,
      run.reasoning,
      run.tool_use,
      run.run_cycle_failures,
      judgeMetadataByCallId,
      toolMetadataByCallId
    );
  }, [
    run.messages,
    run.reasoning,
    run.tool_use,
    run.run_cycle_failures,
    run.scenario_extras,
    scenarioPlugin,
  ]);

  const maxRound = useMemo(
    () => displayEntries.reduce((max, entry) => Math.max(max, entry.round_number), 0),
    [displayEntries]
  );

  const agentColorMap = useMemo(
    () => buildAgentColorMap(run.agents.map(a => a.agent_id)),
    [run.agents]
  );
  const channelColorMap = useMemo(() => buildChannelColorMap(run.channel_ids), [run.channel_ids]);
  const agentInstances = useMemo(
    () => deriveAgentInstances(run.agents, run.agent_swap_events, maxRound, false),
    [run.agents, run.agent_swap_events, maxRound]
  );

  const activeInstance = resolveSelectedInstance(selectedAgent, agentInstances);
  const activeAgentColor = activeInstance ? agentColorMap.get(activeInstance.agent_id) : undefined;

  const handleSelectChannel = useCallback((channel: string | null) => {
    setSelectedChannel(channel);
    setSelectedAgent(null);
  }, []);

  const handleNavigateToMessage = useCallback((messageId: string, channelId: string) => {
    flushSync(() => {
      setSelectedAgent(null);
      setSelectedChannel(channelId);
      setHighlightedMessageId(null);
    });
    setHighlightNonce(nonce => nonce + 1);
    setHighlightedMessageId(messageId);
  }, []);

  const closeTour = useCallback(() => {
    setTourOpen(false);
    setTimelineRound(null);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(TOUR_SEEN_KEY, "1");
    }
  }, []);

  const modelLabel = useMemo(() => {
    const keys = [...new Set(run.agents.map(a => `${a.provider}:${a.model}`))];
    if (keys.length === 1) {
      return keys[0] ?? "unknown";
    }
    if (keys.length === 0) {
      return "unknown";
    }
    return `${keys.length} models`;
  }, [run.agents]);

  const evaluation = run.evaluation;
  const visibleLabels = run.labels.filter(label => !label.startsWith("eval:"));
  const firstAgentId = run.agents[0]?.agent_id ?? null;

  const tourSteps: TourStep[] = [
    {
      target: headerRef,
      title: "The run header",
      body: (
        <>
          This is a run of the <strong>Veyru</strong> scenario — two AI agents coordinating over{" "}
          {maxRound} rounds. The badges are the run&apos;s <strong>knobs</strong> — the scenario
          configuration it used — and the <code>?</code> opens the scenario description.
        </>
      ),
      onEnter: () => handleSelectChannel(null),
    },
    {
      target: sidebarRef,
      title: "Channels and agents",
      body: (
        <>
          The left rail lists the run&apos;s <strong>channels</strong> — the shared spaces agents
          talk in, like <code>#link</code> — and, below them, its <strong>agents</strong>. Click an
          agent to open its full thread.
        </>
      ),
      onEnter: () => handleSelectChannel(null),
    },
    {
      target: () => document.getElementById("agent-thread-drawer"),
      title: "Each agent's system prompt",
      body: (
        <>
          Clicking an agent in the sidebar opens its thread here. It lands on the{" "}
          <strong>System prompt</strong> tab — exactly what the agent was told — and the{" "}
          <strong>Messages</strong> and <strong>Metrics </strong> tabs beside it hold that
          agent&apos;s own messages and scores.
        </>
      ),
      onEnter: () => {
        if (firstAgentId !== null) {
          setSelectedAgent(firstAgentId);
        }
      },
    },
    {
      target: chatRef,
      title: "The transcript",
      body: (
        <>
          The centre pane replays every event by <strong>round → turn</strong>. Amber rows are
          scenario <strong>injections</strong>; you&apos;ll also see agent reasoning, tool calls
          with the judge&apos;s verdict, curved wires linking each notification check to its reply,
          and green/red <strong>pass/fail</strong> pills when a round ends.
        </>
      ),
      onEnter: () => {
        handleSelectChannel(null);
        setTimelineRound(null);
      },
    },
    {
      target: () => document.getElementById("round-timeline-modal"),
      title: "What happened each round",
      body: (
        <>
          Clicking the floating <strong>Round N </strong> button above the transcript opens the
          round&apos;s timeline — what the round <strong>expected</strong> beside what actually{" "}
          <strong>happened</strong>, with each judged action marked accepted or rejected.
        </>
      ),
      onEnter: () => {
        handleSelectChannel("link");
        setTimelineRound(TOUR_TIMELINE_ROUND);
      },
    },
    {
      target: chatRef,
      title: "The postmortem channel",
      body: (
        <>
          Beyond the task channel, this run has a <code>#postmortem </code> channel — a space for
          the agents to step back and coordinate between rounds (here they settle on a shared
          shorthand).
        </>
      ),
      onEnter: () => {
        handleSelectChannel("postmortem");
        setTimelineRound(null);
      },
    },
    {
      target: () => document.getElementById("chat-channel-header"),
      title: "Display options & download",
      body: (
        <>
          The channel toolbar has <strong>display toggles</strong> — the <strong>Reasoning</strong>{" "}
          and <strong>Tools</strong> checkboxes show or hide those entries in the transcript — plus
          a <strong>Download</strong> button that exports the whole run as a zip.
        </>
      ),
      onEnter: () => setSelectedAgent(null),
    },
    {
      target: evalRef,
      title: "Post-hoc evaluation",
      body: (
        <>
          After a run finishes, metrics score it — LLM-as-judge measures and deterministic ones
          alike. Click any metric for its per-round evidence. Here you can see how often the team
          succeeded and how their language changed.
        </>
      ),
      onEnter: () => {
        setSelectedAgent(null);
        setShowEvalPanel(true);
      },
    },
  ];

  return (
    <GroupProvider slug="demo">
      <div className="mx-auto flex h-dvh max-w-7xl min-h-0 flex-col px-4 py-4">
        {/* Demo chrome */}
        <div className="mb-2 flex shrink-0 items-center justify-between">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Back to home
          </Link>
          <button
            type="button"
            onClick={() => setTourOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-[13px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Play className="h-3.5 w-3.5" /> Take the tour
          </button>
        </div>

        {/* Top matter: header, knobs, and labels — spotlighted together in the tour */}
        <div ref={headerRef} className="shrink-0">
          {/* Run header */}
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <span className="flex items-center gap-1.5">
              <h1 className="text-base font-medium">{humanize(run.scenario_name)}</h1>
              <span className="group/help relative">
                <button
                  aria-label="Scenario description"
                  className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  onClick={() => setShowDescription(true)}
                >
                  <HelpCircle className="h-4 w-4" />
                </button>
                <span className="pointer-events-none absolute left-1/2 top-full z-20 mt-1 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg group-hover/help:block">
                  Scenario description
                </span>
              </span>
            </span>
            <span className="text-[13px] text-muted-foreground">
              {formatDayHeader(run.timestamp)} · {maxRound} rounds · {run.total_messages} messages ·{" "}
              {run.agents.length} agents
              {run.total_cost_usd > 0 ? <> · {formatCost(run.total_cost_usd)}</> : null}
              {run.duration_seconds > 0 ? <> · {formatDuration(run.duration_seconds)}</> : null}
              {" · "}
              <span className="group relative cursor-default">
                {modelLabel}
                <span className="pointer-events-none absolute right-0 top-full z-20 mt-1 hidden w-max rounded-md border border-border bg-background px-3 py-2 text-xs shadow-lg group-hover:block">
                  {run.agents.map(agent => (
                    <div key={agent.agent_id} className="flex justify-between gap-4 py-0.5">
                      <span className="text-muted-foreground">{agent.role_name}</span>
                      <span className="font-mono">
                        {agent.provider}:{agent.model}
                      </span>
                    </div>
                  ))}
                </span>
              </span>
            </span>
          </div>

          {/* Scenario config */}
          {Object.keys(run.scenario_config).length > 0 ? (
            <CollapsibleConfigBadges
              containerClassName="mb-3 shrink-0"
              entries={sortConfigEntries(Object.entries(run.scenario_config))}
              toggleClassName="inline-flex items-center rounded-md border border-border bg-muted/50 px-2 py-0.5 text-[12px] text-muted-foreground transition-colors hover:border-primary hover:bg-primary/5"
              renderBadge={([key, value]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setConfigPreview({ key, value: formatConfigValueFull(value) })}
                  className="inline-flex max-w-full items-center gap-1 rounded-md border border-border bg-muted/50 px-2 py-0.5 text-[12px] transition-colors hover:border-primary hover:bg-primary/5"
                >
                  <span className="shrink-0 text-muted-foreground">{humanize(key)}</span>
                  <span className="max-w-64 truncate font-medium">{formatConfigValue(value)}</span>
                </button>
              )}
            />
          ) : null}

          {/* Labels */}
          {visibleLabels.length > 0 ? (
            <div className="mb-3 flex flex-wrap gap-1.5">
              <LabelBadges labels={visibleLabels} size="md" />
            </div>
          ) : null}
        </div>

        {showDescription ? (
          <ScenarioDescriptionModal
            scenarioName={humanize(run.scenario_name)}
            description={run.scenario_description}
            onClose={() => setShowDescription(false)}
          />
        ) : null}

        {/* Shell */}
        <div
          className={cn(
            "relative grid min-h-0 flex-1 rounded-xl border border-border bg-background",
            evaluation !== null && showEvalPanel
              ? "grid-cols-[192px_1fr_280px]"
              : "grid-cols-[192px_1fr]"
          )}
        >
          <div ref={sidebarRef} className="flex min-h-0 flex-col *:min-h-0 *:flex-1">
            <RunSidebar
              channelIds={run.channel_ids}
              agents={run.agents}
              agentInstances={agentInstances}
              selectedChannel={selectedChannel}
              selectedAgent={selectedAgent}
              showLogs={false}
              showEvalLogs={false}
              hasLogs={false}
              hasEvalLogs={false}
              agentColorMap={agentColorMap}
              onSelectChannel={handleSelectChannel}
              onSelectAgent={setSelectedAgent}
              onSelectLogs={() => undefined}
              onSelectEvalLogs={() => undefined}
            />
          </div>

          <div ref={chatRef} className="flex min-h-0 flex-col *:min-h-0 *:flex-1">
            <ChatPane
              exportSlot={
                <Tooltip label="Download run bundle">
                  <a
                    href={DEMO_ZIP_URL}
                    download={`${run.run_id.replace("/", "-")}.zip`}
                    aria-label="Download run bundle"
                    className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  >
                    <Package className="h-3.5 w-3.5" />
                  </a>
                </Tooltip>
              }
              messages={displayEntries}
              agents={run.agents}
              selectedChannel={selectedChannel}
              agentColorMap={agentColorMap}
              channelColorMap={channelColorMap}
              onSelectAgent={setSelectedAgent}
              highlightedMessageId={highlightedMessageId}
              highlightNonce={highlightNonce}
              forkPointMessageId={null}
              swapRoundNumber={null}
              swappedObserverDisplayNames={[]}
              internJoinRoundNumber={null}
              internTakeoverRoundNumber={null}
              replaceAgentRoundStart={null}
              replaceAgentReplacedAgentId={null}
              replaceAgentReplacementModel={null}
              crossRunReplaceRoundStart={null}
              crossRunReplacedAgentId={null}
              crossRunSourceARunId={null}
              crossRunSourceBRunId={null}
              scenarioName={run.scenario_name}
              scenarioExtras={run.scenario_extras}
              roundEndings={run.round_endings}
              roundResults={run.round_results}
              roundInjections={run.round_injections}
              resumeCutoffTimestamp={null}
              agentSwapDividers={[]}
              contextCompactionMarkers={[]}
              activeInstanceRoundRange={
                activeInstance
                  ? { start: activeInstance.round_start, end: activeInstance.round_end }
                  : null
              }
            />
          </div>

          {evaluation !== null && showEvalPanel ? (
            <div ref={evalRef} className="flex min-h-0 flex-col *:min-h-0 *:flex-1">
              <EvalPanel evaluation={evaluation} onClose={() => setShowEvalPanel(false)} />
            </div>
          ) : null}

          {evaluation !== null && !showEvalPanel ? (
            <button
              className="absolute right-2 top-12 z-10 rounded-md border border-border bg-background p-1.5 text-muted-foreground shadow-sm transition-colors hover:bg-muted hover:text-foreground"
              onClick={() => setShowEvalPanel(true)}
              title="Show evaluators panel"
            >
              <PanelRightOpen className="h-4 w-4" />
            </button>
          ) : null}

          {activeInstance && activeAgentColor ? (
            <AgentDrawer
              instance={activeInstance}
              messages={displayEntries}
              agentColor={activeAgentColor}
              channelColorMap={channelColorMap}
              onClose={() => setSelectedAgent(null)}
              onNavigateToMessage={handleNavigateToMessage}
              onNavigateToChannel={channelId => {
                setSelectedAgent(null);
                setSelectedChannel(channelId);
              }}
              measurements={evaluation?.measurements ?? null}
            />
          ) : null}
        </div>

        {configPreview ? (
          <ConfigValueModal
            configKey={configPreview.key}
            value={configPreview.value}
            onClose={() => setConfigPreview(null)}
            secondaryAction={null}
          />
        ) : null}

        {timelineRound !== null ? (
          <RoundTimelineModal
            roundNumber={timelineRound}
            messages={displayEntries.filter(entry => entry.round_number === timelineRound)}
            scenarioName={run.scenario_name}
            scenarioExtras={run.scenario_extras}
            roundEnding={
              run.round_endings.find(ending => ending.round_number === timelineRound) ?? null
            }
            onClose={() => setTimelineRound(null)}
          />
        ) : null}
      </div>

      {tourOpen ? <GuidedTour steps={tourSteps} onClose={closeTour} /> : null}
    </GroupProvider>
  );
}
