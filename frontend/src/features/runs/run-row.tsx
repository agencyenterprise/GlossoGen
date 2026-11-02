"use client";

import { memo, useState, type MouseEvent, type ReactNode } from "react";
import {
  Check,
  Copy,
  GitFork,
  Package,
  Repeat,
  RotateCcw,
  StickyNote,
  Sword,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";
import { Tooltip } from "@/shared/components/ui/tooltip";
import { downloadAuthenticatedFile } from "@/shared/lib/api-client";
import { cn } from "@/shared/lib/cn";
import { splitRunId } from "@/shared/lib/run-id";
import type { components } from "@/types/api.gen";
import { AgentModelsBadge } from "./agent-models-badge";
import { LabelBadges } from "./eval-label-group";
import { EvaluationBadge } from "./evaluation-badge";
import {
  elapsedSince,
  formatConfigValue,
  formatCost,
  formatDuration,
  formatTime,
  humanize,
} from "./format";
import { RoundSuccessMeter } from "./round-success-meter";
import { RunInfoDropdown } from "./run-info-dropdown";
import { RunKnobsDropdown } from "./run-knobs-dropdown";

type RunSummary = components["schemas"]["RunSummary"];
type RunStatus = components["schemas"]["RunStatus"];

/** Props for a single run row. Every callback is expected to be referentially
 *  stable in the parent so ``React.memo`` can skip re-rendering unaffected rows
 *  (e.g. when a sibling row's hover popover mutates parent state). */
export interface RunRowProps {
  run: RunSummary;
  onNavigate: (runId: string, event: MouseEvent) => void;
  onStop: (runId: string) => void;
  onDelete: (runId: string) => void;
  onShowNote: (runId: string) => void;
  onConfigPreview: (preview: { key: string; value: string }) => void;
  /** Knobs the active conditions ask about. Each row shows what it recorded for
   *  them, so a filtered list says why each run is in it. */
  shownKnobs: string[];
  picking: boolean;
  selected: boolean;
  onToggleSelected: (runId: string) => void;
}

/** How each status other than ``scenario_complete`` reads. A completed run, which
 *  is nearly every run, shows no status at all. */
const STATUS_STYLES: Partial<Record<RunStatus, { label: string; dot: string; text: string }>> = {
  in_progress: {
    label: "In Progress",
    dot: "animate-pulse bg-green-500",
    text: "text-green-700 dark:text-green-400",
  },
  starting: {
    label: "Starting",
    dot: "animate-pulse bg-sky-500",
    text: "text-sky-700 dark:text-sky-400",
  },
  error: { label: "Error", dot: "bg-red-500", text: "text-destructive" },
  killed: { label: "Killed", dot: "bg-zinc-400", text: "text-muted-foreground" },
};

function RunStatusPill({ status }: { status: RunStatus }) {
  const style = STATUS_STYLES[status];
  if (style === undefined) {
    return null;
  }
  return (
    <span className={cn("inline-flex items-center gap-1 text-[11px] font-medium", style.text)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", style.dot)} />
      {style.label}
    </span>
  );
}

/** One way the run departs from a plain run of its scenario: a derivation from
 *  another run, or a mode that changes who plays mid-run. */
type RunLineage = { key: string; icon: ReactNode; text: string; detail: string; tone: string };

function buildLineage(run: RunSummary): RunLineage[] {
  const cfg = run.scenario_config ?? {};
  const icon = "h-3 w-3";
  const lineage: RunLineage[] = [];
  if (run.fork_source) {
    lineage.push({
      key: "fork",
      icon: <GitFork className={icon} />,
      text: "Fork",
      detail: "Forked from another run",
      tone: "text-violet-700 dark:text-violet-400",
    });
  }
  if (run.replace_agent_source) {
    const source = run.replace_agent_source;
    lineage.push({
      key: "replaced",
      icon: <Repeat className={icon} />,
      text: `Replaced ${source.replaced_agent_id} after R${source.after_round}`,
      detail: `Replaced ${source.replaced_agent_id} after round ${source.after_round}`,
      tone: "text-sky-700 dark:text-sky-400",
    });
  }
  if (run.cross_run_replace_agent_source) {
    const source = run.cross_run_replace_agent_source;
    lineage.push({
      key: "cross-run",
      icon: <Repeat className={icon} />,
      text: `Imported ${source.replaced_agent_id} after R${source.after_round}`,
      detail: `Imported ${source.replaced_agent_id} from ${source.source_b_run_id} (through end of round ${source.source_b_round_end}) after round ${source.after_round}`,
      tone: "text-violet-700 dark:text-violet-400",
    });
  }
  if (run.fork_at_round_source) {
    const source = run.fork_at_round_source;
    lineage.push({
      key: "forked-at-round",
      icon: <RotateCcw className={icon} />,
      text: `Forked after R${source.after_round}`,
      detail: `Forked after round ${source.after_round}, played ${source.rounds_after} round${source.rounds_after === 1 ? "" : "s"} after`,
      tone: "text-emerald-700 dark:text-emerald-400",
    });
  }
  if (cfg.intern_enabled === true) {
    const round = cfg.intern_takeover_round;
    lineage.push({
      key: "intern",
      icon: <UserPlus className={icon} />,
      text: typeof round === "number" ? `Intern at R${round}` : "Intern",
      detail: typeof round === "number" ? `Intern takeover at round ${round}` : "Intern enabled",
      tone: "text-amber-700 dark:text-amber-400",
    });
  }
  if (cfg.two_teams === true) {
    const round = cfg.swap_round;
    lineage.push({
      key: "swap",
      icon: <Users className={icon} />,
      text: typeof round === "number" ? `Swap at R${round}` : "Two teams",
      detail: typeof round === "number" ? `Observer swap at round ${round}` : "Two-team mode",
      tone: "text-emerald-700 dark:text-emerald-400",
    });
  }
  return lineage;
}

/** The run's elapsed time: its recorded duration, or the time since it started
 *  while it is still running. Null when the run recorded neither. */
function resolveDurationText(run: RunSummary): string | null {
  if (run.duration_seconds > 0) {
    return formatDuration(run.duration_seconds);
  }
  if (run.status === "in_progress") {
    return formatDuration(elapsedSince(run.timestamp));
  }
  return null;
}

/** The line under a run's start time: how long it ran and what it cost. Null when
 *  the run recorded neither. */
export function resolveRunDetailLine(run: RunSummary): string | null {
  const parts: string[] = [];
  const duration = resolveDurationText(run);
  if (duration !== null) {
    parts.push(duration);
  }
  if (run.total_cost_usd > 0) {
    parts.push(formatCost(run.total_cost_usd));
  }
  if (parts.length === 0) {
    return null;
  }
  return parts.join(" · ");
}

/** Where the run is in its rounds, for a run still going or one whose scenario
 *  judges no rounds. Null when no round has started. */
function resolveRoundText(run: RunSummary): string | null {
  if (run.current_round <= 0) {
    return null;
  }
  const totalRound = run.scenario_config?.round_count;
  if (run.status === "in_progress" && typeof totalRound === "number") {
    return `Round ${run.current_round} / ${totalRound}`;
  }
  return `${run.current_round} ${run.current_round === 1 ? "round" : "rounds"}`;
}

function RowAction({
  label,
  danger,
  onClick,
  children,
}: {
  label: string;
  danger: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Tooltip label={label} wrap={false}>
      <button
        type="button"
        aria-label={label}
        className={cn(
          "rounded p-1 text-muted-foreground transition-colors",
          danger
            ? "hover:bg-destructive/10 hover:text-destructive"
            : "hover:bg-muted hover:text-foreground"
        )}
        onClick={e => {
          e.stopPropagation();
          onClick();
        }}
      >
        {children}
      </button>
    </Tooltip>
  );
}

function RunRowComponent({
  run,
  onNavigate,
  onStop,
  onDelete,
  onShowNote,
  onConfigPreview,
  shownKnobs,
  picking,
  selected,
  onToggleSelected,
}: RunRowProps) {
  const [copied, setCopied] = useState(false);
  const statusBgClass = run.status === "in_progress" ? "bg-green-50 dark:bg-green-950/20" : "";
  // One background wins outright, so precedence does not depend on stylesheet order.
  const bgClass = picking && selected ? "bg-primary/5 dark:bg-primary/10" : statusBgClass;

  const handleRowClick = (event: MouseEvent) => {
    if (picking) {
      onToggleSelected(run.run_id);
      return;
    }
    onNavigate(run.run_id, event);
  };
  const lineage = buildLineage(run);
  const detailLine = resolveRunDetailLine(run);
  const roundText = resolveRoundText(run);
  const hasRoundResults = run.round_results.length > 0;
  const config = run.scenario_config ?? {};

  return (
    <div
      className={cn(
        "group flex cursor-pointer items-center gap-6 px-4 py-2.5 text-sm transition-colors hover:bg-accent/50",
        bgClass
      )}
      onClick={handleRowClick}
    >
      {picking ? (
        <span className="-mr-3 flex shrink-0" onClick={e => e.stopPropagation()}>
          <input
            type="checkbox"
            aria-label={`Select ${run.run_id}`}
            checked={selected}
            onChange={() => onToggleSelected(run.run_id)}
            className="rounded border-input"
          />
        </span>
      ) : null}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <span className="font-medium">{humanize(run.scenario_name)}</span>
          <span className="inline-flex items-center gap-0.5">
            <span className="font-mono text-[10px] text-muted-foreground">
              {splitRunId(run.run_id).run_dir_name}
            </span>
            <button
              type="button"
              aria-label="Copy run ID"
              title={copied ? "Copied!" : "Copy run ID"}
              className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              onClick={e => {
                e.stopPropagation();
                void navigator.clipboard.writeText(run.run_id);
                setCopied(true);
                window.setTimeout(() => setCopied(false), 2000);
              }}
            >
              {copied ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}
            </button>
          </span>
          <RunStatusPill status={run.status} />
          {lineage.map(item => (
            <Tooltip key={item.key} label={item.detail} wrap={true}>
              <span
                className={cn(
                  "inline-flex items-center gap-1 whitespace-nowrap text-[11px]",
                  item.tone
                )}
              >
                {item.icon}
                {item.text}
              </span>
            </Tooltip>
          ))}
          {run.has_note ? (
            <button
              type="button"
              className="inline-flex items-center gap-1 rounded-full bg-yellow-100 px-1.5 py-0.5 text-[10px] font-medium text-yellow-700 transition-colors hover:bg-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:hover:bg-yellow-900/50"
              onClick={e => {
                e.stopPropagation();
                onShowNote(run.run_id);
              }}
            >
              <StickyNote className="h-2.5 w-2.5" />
              Note
            </button>
          ) : null}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
          <AgentModelsBadge agentModels={run.agent_models} />
          <span className="inline-flex items-center gap-1" onClick={e => e.stopPropagation()}>
            <RunInfoDropdown
              timestamp={run.timestamp}
              roundCount={run.current_round}
              messageCount={run.total_messages}
              eventCount={null}
              agents={run.agent_models.map(agent => ({ ...agent, model_settings: null }))}
              totalCostUsd={run.total_cost_usd}
              durationSeconds={run.duration_seconds}
              tokenUsage={null}
              align="left"
            />
            {Object.keys(config).length > 0 ? (
              <RunKnobsDropdown
                scenarioConfig={config}
                align="left"
                onOpenValue={(key, value) => onConfigPreview({ key, value })}
              />
            ) : null}
          </span>
          {shownKnobs.map(knob => {
            if (!(knob in config)) {
              return null;
            }
            return (
              <span
                key={knob}
                className="inline-flex items-center gap-1 rounded border border-border bg-muted/50 px-1.5 py-0 text-[11px]"
              >
                <span className="text-muted-foreground">{humanize(knob)}</span>
                <span className="font-medium tabular-nums">{formatConfigValue(config[knob])}</span>
              </span>
            );
          })}
          <LabelBadges labels={run.labels.filter(label => !label.startsWith("eval:"))} size="sm" />
        </div>
      </div>
      <div className="flex w-44 shrink-0 flex-col gap-0.5">
        {hasRoundResults ? <RoundSuccessMeter tallies={run.round_results} /> : null}
        {roundText !== null && (!hasRoundResults || run.status === "in_progress") ? (
          <span className="font-mono text-[10px] text-muted-foreground">{roundText}</span>
        ) : null}
      </div>
      <div className="w-28 shrink-0 text-right">
        <div className="text-xs text-muted-foreground">{formatTime(run.timestamp)}</div>
        {detailLine !== null ? (
          <div className="font-mono text-[10px] text-muted-foreground">{detailLine}</div>
        ) : null}
      </div>
      <div className="flex w-20 shrink-0 justify-end">
        {run.has_evaluation ? <EvaluationBadge scores={run.evaluation_scores} /> : null}
      </div>
      <div className="flex w-[4.5rem] shrink-0 items-center justify-end gap-0.5">
        {run.status === "in_progress" ? (
          <RowAction label="Stop simulation" danger={true} onClick={() => onStop(run.run_id)}>
            <Sword className="h-3.5 w-3.5" />
          </RowAction>
        ) : null}
        <span className="inline-flex items-center gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
          <RowAction
            label="Export bundle"
            danger={false}
            onClick={() =>
              void downloadAuthenticatedFile({
                path: `/api/g/{group_slug}/runs/${run.run_id}/export/zip`,
                searchParams: new URLSearchParams(),
                fallbackFilename: `${splitRunId(run.run_id).run_dir_name}.zip`,
              })
            }
          >
            <Package className="h-3.5 w-3.5" />
          </RowAction>
          <RowAction label="Delete run" danger={true} onClick={() => onDelete(run.run_id)}>
            <Trash2 className="h-3.5 w-3.5" />
          </RowAction>
        </span>
      </div>
    </div>
  );
}

export const RunRow = memo(RunRowComponent);
