"use client";

import { useCallback, useEffect, useState } from "react";
import { flushSync } from "react-dom";
import {
  ArrowLeft,
  Check,
  Copy,
  Download,
  FlaskConical,
  HelpCircle,
  Loader2,
  Package,
  PanelRightOpen,
  Pencil,
  Radio,
  StickyNote,
  Sword,
  Tag,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Tooltip } from "@/shared/components/ui/tooltip";
import { downloadAuthenticatedFile } from "@/shared/lib/api-client";
import { cn } from "@/shared/lib/cn";
import { splitRunId } from "@/shared/lib/run-id";
import { useServerConfig } from "@/shared/lib/use-server-config";
import { useGroupPath } from "@/features/auth/group-context";
import { AgentDrawer } from "./agent-drawer";
import { resolveSelectedInstance } from "./agent-instance";
import { ChatPane } from "./chat-pane";
import { CollapsibleConfigBadges } from "./collapsible-config-badges";
import { LabelBadges } from "./eval-label-group";
import { EvalLogPanel } from "./eval-log-panel";
import { EvalPanel } from "./eval-panel";
import { ForkBadge } from "./fork-badge";
import { RunTimelineFabs } from "./run-timeline-fabs";
import { StartEvaluationModal } from "./start-evaluation-modal";
import {
  elapsedSince,
  formatConfigValue,
  formatConfigValueFull,
  formatCost,
  formatDayHeader,
  formatDuration,
  humanize,
  sortConfigEntries,
} from "./format";
import { LogPanel } from "./log-panel";
import { RunSidebar } from "./run-sidebar";
import { getScenarioPlugin } from "./scenario-registry";
import { useRunDetailData } from "./use-run-detail-data";
import { ScenarioDescriptionModal } from "./scenario-description-modal";
import { ReplaceAgentBadge } from "./replace-agent-badge";
import { CrossRunReplaceAgentBadge } from "./cross-run-replace-agent-badge";
import { ResumeAtRoundBadge } from "./resume-at-round-badge";
import { DerivedRunsSection } from "./derived-runs-section";
import { ConfigValueModal } from "./config-value-modal";
import { LabelPickerModal } from "./label-picker-modal";
import { NoteEditorModal } from "./note-editor-modal";

export function RunDetail({ scenario, runDirName }: { scenario: string; runDirName: string }) {
  const groupPath = useGroupPath();
  const scenarioPlugin = getScenarioPlugin(scenario);
  const [configPreview, setConfigPreview] = useState<{ key: string; value: string } | null>(null);
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [highlightedMessageId, setHighlightedMessageId] = useState<string | null>(null);
  const [highlightNonce, setHighlightNonce] = useState(0);
  const [showDescription, setShowDescription] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const [showEvalLogs, setShowEvalLogs] = useState(false);
  const [showEvalPanel, setShowEvalPanel] = useState(true);
  const [showEvalModal, setShowEvalModal] = useState(false);
  const [evalJustLaunched, setEvalJustLaunched] = useState(false);
  const [copiedRunId, setCopiedRunId] = useState(false);
  const [showLabelPicker, setShowLabelPicker] = useState(false);
  const [showNoteEditor, setShowNoteEditor] = useState(false);

  const { data: serverConfig } = useServerConfig();
  // Treat undefined (still loading) as enabled so the button only hides when
  // the server explicitly reports evaluations disabled.
  const evaluationsEnabled = serverConfig?.evaluations_enabled !== false;

  const searchParams = useSearchParams();

  const {
    runId,
    restData,
    isLoading,
    error,
    sseConnected,
    effectiveStatus,
    isInProgress,
    runCompleted,
    displayEntries,
    allAgents,
    allChannelIds,
    agentInstances,
    agentSwapDividers,
    contextCompactionMarkers,
    agentColorMap,
    channelColorMap,
    allDebugLogs,
    scenarioMarkers,
    swapEvents,
    maxRound,
    modelLabel,
    channelMessages,
    timelineEntries,
    totalCostUsd,
    durationSeconds,
    stopMutation,
  } = useRunDetailData({ scenario, runDirName, scenarioPlugin, evalJustLaunched });

  const handleSelectChannel = useCallback((ch: string | null) => {
    setSelectedChannel(ch);
    setSelectedAgent(null);
    setShowLogs(false);
    setShowEvalLogs(false);
  }, []);

  function handleNavigateToMessage(messageId: string, channelId: string) {
    flushSync(() => {
      setSelectedAgent(null);
      setSelectedChannel(channelId);
      setShowLogs(false);
      setShowEvalLogs(false);
      setHighlightedMessageId(null);
    });
    setHighlightNonce(n => n + 1);
    setHighlightedMessageId(messageId);
  }

  // Auto-highlight a message from ?highlight= query param (e.g. from branches viewer)
  const highlightParam = searchParams.get("highlight");
  const [didAutoHighlight, setDidAutoHighlight] = useState(false);
  useEffect(() => {
    if (!highlightParam || didAutoHighlight || displayEntries.length === 0) {
      return;
    }
    requestAnimationFrame(() => {
      setDidAutoHighlight(true);
      setHighlightNonce(n => n + 1);
      setHighlightedMessageId(highlightParam);
    });
  }, [highlightParam, didAutoHighlight, displayEntries.length]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !restData) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-20 text-destructive">
        <XCircle className="h-8 w-8" />
        <p>Failed to load run</p>
      </div>
    );
  }

  const evaluation = restData.evaluation;
  const evaluationInProgress = restData.evaluation_in_progress || evalJustLaunched;
  const hasLogs = allDebugLogs.length > 0;
  const hasEvalLogs = evaluationInProgress || evaluation !== null || restData.has_eval_log_file;
  const activeInstance = resolveSelectedInstance(selectedAgent, agentInstances);
  const activeAgentColor = activeInstance ? agentColorMap.get(activeInstance.agent_id) : undefined;

  const scrollToDivider = (elementId: string) => {
    flushSync(() => {
      setSelectedAgent(null);
      setShowLogs(false);
      setSelectedChannel(null);
      setHighlightedMessageId(null);
    });
    requestAnimationFrame(() => {
      const el = document.getElementById(elementId);
      if (!el) return;
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("animate-highlight");
      setTimeout(() => {
        el.classList.remove("animate-highlight");
      }, 1500);
    });
  };

  const handleNavigateToForkPoint = (targetMessageId: string) => {
    const entry = displayEntries.find(e => e.message_id === targetMessageId);
    if (!entry) return;
    const needsChannelSwitch = selectedChannel !== null && selectedChannel !== entry.channel_id;
    flushSync(() => {
      setSelectedAgent(null);
      setShowLogs(false);
      if (needsChannelSwitch) {
        setSelectedChannel(null);
      }
      setHighlightedMessageId(null);
    });
    setHighlightNonce(n => n + 1);
    setHighlightedMessageId(targetMessageId);
  };

  return (
    <div className="flex h-dvh min-h-0 w-full flex-col px-4 py-4 lg:px-8 2xl:px-12">
      {/* Back link */}
      <Link
        href={groupPath("/runs")}
        className="mb-2 inline-flex shrink-0 items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> back to runs
      </Link>

      {/* Header */}
      <div className="mb-3 flex shrink-0 flex-wrap items-baseline justify-between gap-2">
        <span className="flex items-center gap-1.5">
          <h1 className="text-base font-medium">{humanize(restData.scenario_name)}</h1>
          {restData.fork_source ? (
            <ForkBadge
              sourceRunId={restData.fork_source.source_run_id}
              targetMessageId={restData.fork_source.target_message_id}
            />
          ) : null}
          {restData.replace_agent_source ? (
            <ReplaceAgentBadge
              sourceRunId={restData.replace_agent_source.source_run_id}
              replacedAgentId={restData.replace_agent_source.replaced_agent_id}
              replacementModel={restData.replace_agent_source.replacement_model}
              roundStart={restData.replace_agent_source.round_start}
            />
          ) : null}
          {restData.cross_run_replace_agent_source ? (
            <CrossRunReplaceAgentBadge
              sourceARunId={restData.cross_run_replace_agent_source.source_a_run_id}
              sourceBRunId={restData.cross_run_replace_agent_source.source_b_run_id}
              replacedAgentId={restData.cross_run_replace_agent_source.replaced_agent_id}
              importedModel={restData.cross_run_replace_agent_source.imported_model}
              roundStart={restData.cross_run_replace_agent_source.round_start}
              sourceBRoundEnd={restData.cross_run_replace_agent_source.source_b_round_end}
            />
          ) : null}
          {restData.resume_at_round_source ? (
            <ResumeAtRoundBadge
              sourceRunId={restData.resume_at_round_source.source_run_id}
              roundStart={restData.resume_at_round_source.round_start}
              roundsAfterResume={restData.resume_at_round_source.rounds_after_resume}
            />
          ) : null}
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
          <span className="group/copy relative">
            <button
              aria-label="Copy run ID"
              className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              onClick={() => {
                navigator.clipboard.writeText(runId);
                setCopiedRunId(true);
                setTimeout(() => setCopiedRunId(false), 2000);
              }}
            >
              {copiedRunId ? (
                <Check className="h-4 w-4 text-green-500" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </button>
            <span className="pointer-events-none absolute left-1/2 top-full z-20 mt-1 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg group-hover/copy:block">
              {copiedRunId ? "Copied!" : "Copy run ID"}
            </span>
          </span>
        </span>
        <span className="text-[13px] text-muted-foreground">
          {formatDayHeader(restData.timestamp)} · {maxRound} rounds · {channelMessages} messages ·{" "}
          {timelineEntries} events · {allAgents.length} agents
          {totalCostUsd > 0 ? <> · {formatCost(totalCostUsd)}</> : null}
          {durationSeconds > 0 ? <> · {formatDuration(durationSeconds)}</> : null}
          {" · "}
          <span className="group relative cursor-default">
            {modelLabel}
            <span className="pointer-events-none absolute right-0 top-full z-20 mt-1 hidden w-max rounded-md border border-border bg-background px-3 py-2 text-xs shadow-lg group-hover:block">
              {allAgents.map(a => (
                <div key={a.agent_id} className="flex justify-between gap-4 py-0.5">
                  <span className="text-muted-foreground">{a.role_name}</span>
                  <span className="font-mono">
                    {a.provider}:{a.model}
                  </span>
                </div>
              ))}
            </span>
          </span>
          {!isInProgress && !evaluationInProgress && runCompleted && evaluationsEnabled ? (
            <>
              {" · "}
              <span className="group/eval relative">
                <button
                  className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-[12px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  onClick={() => setShowEvalModal(true)}
                >
                  <FlaskConical className="h-3 w-3" />
                  {evaluation !== null ? "Re-run Eval" : "Run Eval"}
                </button>
                <span className="pointer-events-none absolute left-1/2 top-full z-20 mt-1 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg group-hover/eval:block">
                  {evaluation !== null
                    ? "Re-run LLM-as-judge evaluation"
                    : "Run LLM-as-judge evaluation"}
                </span>
              </span>
            </>
          ) : null}
          {" · "}
          <button
            className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-[12px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={() => setShowLabelPicker(true)}
          >
            <Tag className="h-3 w-3" />
            Labels
          </button>
          {" · "}
          <button
            className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-[12px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={() => setShowNoteEditor(true)}
          >
            {restData.note ? <Pencil className="h-3 w-3" /> : <StickyNote className="h-3 w-3" />}
            {restData.note ? "Edit Note" : "Add Note"}
          </button>
        </span>
      </div>

      {/* Derived runs (children) */}
      <DerivedRunsSection derivedRuns={restData.children} />

      {/* Scenario config */}
      {restData.scenario_config && Object.keys(restData.scenario_config).length > 0 ? (
        <CollapsibleConfigBadges
          containerClassName="mb-3 shrink-0"
          entries={sortConfigEntries(Object.entries(restData.scenario_config))}
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

      {/* Regular labels (eval:* legacy labels are filtered out) */}
      {restData.labels.some(label => !label.startsWith("eval:")) ? (
        <div className="mb-3 flex shrink-0 flex-wrap gap-1.5">
          <LabelBadges
            labels={restData.labels.filter(label => !label.startsWith("eval:"))}
            size="md"
          />
        </div>
      ) : null}

      {showDescription ? (
        <ScenarioDescriptionModal
          scenarioName={humanize(restData.scenario_name)}
          description={restData.scenario_description}
          onClose={() => setShowDescription(false)}
        />
      ) : null}

      {/* Live streaming banner */}
      {isInProgress ? (
        <div className="mb-2 flex shrink-0 items-center gap-2 rounded-lg border border-yellow-300/50 bg-yellow-50 px-3 py-1.5 text-xs text-yellow-800 dark:border-yellow-700/50 dark:bg-yellow-950/30 dark:text-yellow-300">
          {sseConnected ? (
            <Radio className="h-3 w-3 text-green-600 dark:text-green-400" />
          ) : (
            <Loader2 className="h-3 w-3 animate-spin" />
          )}
          <span>
            Simulation in progress
            {sseConnected ? " — streaming live" : " — connecting..."}
            {restData ? <> · {formatDuration(elapsedSince(restData.timestamp))}</> : null}
          </span>
          {effectiveStatus !== "starting" ? (
            <span className="group/stop relative ml-auto">
              <button
                className="rounded p-1 transition-colors hover:bg-yellow-200 dark:hover:bg-yellow-800/50"
                aria-label="Stop simulation"
                onClick={() => stopMutation.mutate()}
              >
                <Sword className="h-3 w-3" />
              </button>
              <span className="pointer-events-none absolute left-1/2 top-full z-20 mt-1 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg group-hover/stop:block">
                Stop simulation
              </span>
            </span>
          ) : null}
        </div>
      ) : null}

      {/* Evaluation in-progress banner */}
      {!isInProgress && evaluationInProgress ? (
        <div className="mb-2 flex shrink-0 items-center gap-2 rounded-lg border border-blue-300/50 bg-blue-50 px-3 py-1.5 text-xs text-blue-800 dark:border-blue-700/50 dark:bg-blue-950/30 dark:text-blue-300">
          <Loader2 className="h-3 w-3 animate-spin" />
          <span>Evaluation in progress...</span>
        </div>
      ) : null}

      {/* Shell */}
      <div
        className={cn(
          "relative grid min-h-0 flex-1 rounded-xl border border-border bg-background *:min-h-0",
          evaluation !== null && showEvalPanel
            ? "grid-cols-[240px_1fr_280px]"
            : "grid-cols-[240px_1fr]"
        )}
      >
        <RunSidebar
          channelIds={allChannelIds}
          agents={allAgents}
          agentInstances={agentInstances}
          selectedChannel={selectedChannel}
          selectedAgent={selectedAgent}
          showLogs={showLogs}
          showEvalLogs={showEvalLogs}
          hasLogs={hasLogs}
          hasEvalLogs={hasEvalLogs}
          agentColorMap={agentColorMap}
          onSelectChannel={handleSelectChannel}
          onSelectAgent={setSelectedAgent}
          onSelectLogs={() => {
            setShowLogs(true);
            setShowEvalLogs(false);
            setSelectedAgent(null);
          }}
          onSelectEvalLogs={() => {
            setShowEvalLogs(true);
            setShowLogs(false);
            setSelectedAgent(null);
          }}
        />

        {/* Main content: chat, logs, or eval logs */}
        {showLogs ? (
          <LogPanel logs={allDebugLogs} />
        ) : showEvalLogs ? (
          <EvalLogPanel runId={runId} evaluationInProgress={evaluationInProgress} />
        ) : (
          <ChatPane
            exportSlot={
              <>
                <span className="group/pdf relative">
                  <button
                    aria-label="Export PDF"
                    className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                    onClick={() => {
                      const params = new URLSearchParams();
                      if (selectedChannel !== null) {
                        params.set("channel_id", selectedChannel);
                      }
                      void downloadAuthenticatedFile({
                        path: `/api/g/{group_slug}/runs/${runId}/export/pdf`,
                        searchParams: params,
                        fallbackFilename: `${runId.slice(0, 8)}_transcript.pdf`,
                      });
                    }}
                  >
                    <Download className="h-3.5 w-3.5" />
                  </button>
                  <span className="pointer-events-none absolute left-1/2 top-full z-50 mt-1 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg group-hover/pdf:block">
                    Export PDF
                  </span>
                </span>
                <Tooltip label="Export run bundle">
                  <button
                    aria-label="Export bundle"
                    className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                    onClick={() => {
                      void downloadAuthenticatedFile({
                        path: `/api/g/{group_slug}/runs/${runId}/export/zip`,
                        searchParams: new URLSearchParams(),
                        fallbackFilename: `${splitRunId(runId).run_dir_name}.zip`,
                      });
                    }}
                  >
                    <Package className="h-3.5 w-3.5" />
                  </button>
                </Tooltip>
              </>
            }
            messages={displayEntries}
            agents={allAgents}
            selectedChannel={selectedChannel}
            agentColorMap={agentColorMap}
            channelColorMap={channelColorMap}
            onSelectAgent={setSelectedAgent}
            highlightedMessageId={highlightedMessageId}
            highlightNonce={highlightNonce}
            forkPointMessageId={restData.fork_source?.target_message_id ?? null}
            scenarioMarkers={scenarioMarkers}
            replaceAgentSource={restData.replace_agent_source}
            crossRunReplaceAgentSource={restData.cross_run_replace_agent_source}
            scenarioName={restData.scenario_name}
            scenarioExtras={restData.scenario_extras ?? null}
            roundEndings={restData.round_endings}
            roundResults={restData.round_results}
            roundInjections={restData.round_injections}
            resumeCutoffTimestamp={
              restData.replace_agent_source?.replaced_at ?? restData.fork_source?.forked_at ?? null
            }
            agentSwapDividers={agentSwapDividers}
            contextCompactionMarkers={contextCompactionMarkers}
            activeInstanceRoundRange={
              activeInstance
                ? { start: activeInstance.round_start, end: activeInstance.round_end }
                : null
            }
          />
        )}

        {/* Right panel: eval (completed) */}
        {!isInProgress && evaluation !== null && showEvalPanel ? (
          <EvalPanel evaluation={evaluation} onClose={() => setShowEvalPanel(false)} />
        ) : null}

        {/* Right panel toggle (when hidden) */}
        {!isInProgress && evaluation !== null && !showEvalPanel ? (
          <button
            className="absolute right-2 top-12 z-10 rounded-md border border-border bg-background p-1.5 text-muted-foreground shadow-sm transition-colors hover:bg-muted hover:text-foreground"
            onClick={() => setShowEvalPanel(true)}
            title="Show evaluators panel"
          >
            <PanelRightOpen className="h-4 w-4" />
          </button>
        ) : null}

        {/* Agent drawer */}
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
            measurements={restData.evaluation?.measurements ?? null}
          />
        ) : null}
      </div>

      {/* Start evaluation modal */}
      {showEvalModal && evaluationsEnabled ? (
        <StartEvaluationModal
          runId={runId}
          scenarioName={restData.scenario_name}
          onClose={() => setShowEvalModal(false)}
          onLaunched={() => {
            setEvalJustLaunched(true);
            setTimeout(() => setEvalJustLaunched(false), 30_000);
          }}
        />
      ) : null}

      {showLabelPicker ? (
        <LabelPickerModal
          runId={runId}
          currentLabels={restData.labels}
          onClose={() => setShowLabelPicker(false)}
        />
      ) : null}

      {showNoteEditor ? (
        <NoteEditorModal
          runId={runId}
          initialContent={restData.note ?? null}
          onClose={() => setShowNoteEditor(false)}
        />
      ) : null}

      {configPreview ? (
        <ConfigValueModal
          configKey={configPreview.key}
          value={configPreview.value}
          onClose={() => setConfigPreview(null)}
          secondaryAction={null}
        />
      ) : null}

      <RunTimelineFabs
        forkSource={restData.fork_source}
        replaceAgentSource={restData.replace_agent_source}
        crossRunReplaceAgentSource={restData.cross_run_replace_agent_source}
        scenarioMarkers={scenarioMarkers}
        swapEvents={swapEvents}
        onScrollToDivider={scrollToDivider}
        onNavigateToForkPoint={handleNavigateToForkPoint}
      />
    </div>
  );
}
