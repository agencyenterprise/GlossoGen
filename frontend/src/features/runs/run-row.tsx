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
import { downloadAuthenticatedFile } from "@/shared/lib/api-client";
import { cn } from "@/shared/lib/cn";
import { splitRunId } from "@/shared/lib/run-id";
import type { components } from "@/types/api.gen";
import {
  elapsedSince,
  formatConfigValue,
  formatCost,
  formatDuration,
  formatTime,
  humanize,
} from "./format";
import { LabelBadges } from "./eval-label-group";
import { EvaluationBadge } from "./evaluation-badge";
import { RunKnobsDropdown } from "./run-knobs-dropdown";

type RunSummary = components["schemas"]["RunSummary"];
type RunStatus = components["schemas"]["RunStatus"];

export const STATUS_LABELS: Record<RunStatus, string> = {
  scenario_complete: "Completed",
  in_progress: "In Progress",
  starting: "Starting",
  error: "Error",
  killed: "Killed",
};

/** Props for a single run row. Every callback is expected to be referentially
 *  stable in the parent so ``React.memo`` can skip re-rendering unaffected rows
 *  (e.g. when a sibling row's hover popover mutates parent state). */
export interface RunRowProps {
  run: RunSummary;
  showTopBorder: boolean;
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

function buildStatusBadges(run: RunSummary): ReactNode[] {
  const cfg = run.scenario_config ?? {};
  const badges: ReactNode[] = [];
  if (run.replace_agent_source) {
    badges.push(
      <span
        key="replaced"
        title={`Replaced ${run.replace_agent_source.replaced_agent_id} after round ${run.replace_agent_source.after_round}`}
        className="inline-flex items-center gap-0.5 text-sky-700 dark:text-sky-400"
      >
        <Repeat className="h-2.5 w-2.5" />R{run.replace_agent_source.after_round}
      </span>
    );
  }
  if (run.cross_run_replace_agent_source) {
    const cr = run.cross_run_replace_agent_source;
    badges.push(
      <span
        key="cross-run"
        title={`Cross-run: imported ${cr.replaced_agent_id} from ${cr.source_b_run_id} (through end of round ${cr.source_b_round_end}) after round ${cr.after_round}`}
        className="inline-flex items-center gap-0.5 text-violet-700 dark:text-violet-400"
      >
        <Repeat className="h-2.5 w-2.5" />R{cr.after_round}
      </span>
    );
  }
  if (run.fork_at_round_source) {
    const fr = run.fork_at_round_source;
    badges.push(
      <span
        key="forked-at-round"
        title={`Forked after round ${fr.after_round}, played ${fr.rounds_after} round${fr.rounds_after === 1 ? "" : "s"} after`}
        className="inline-flex items-center gap-0.5 text-emerald-700 dark:text-emerald-400"
      >
        <RotateCcw className="h-2.5 w-2.5" />R{fr.after_round}
      </span>
    );
  }
  if (cfg.intern_enabled === true) {
    const round = cfg.intern_takeover_round;
    badges.push(
      <span
        key="intern"
        title={typeof round === "number" ? `Intern takeover at round ${round}` : "Intern enabled"}
        className="inline-flex items-center gap-0.5 text-amber-700 dark:text-amber-400"
      >
        <UserPlus className="h-2.5 w-2.5" />
        {typeof round === "number" ? `R${round}` : ""}
      </span>
    );
  }
  if (cfg.two_teams === true) {
    const round = cfg.swap_round;
    badges.push(
      <span
        key="swap"
        title={typeof round === "number" ? `Observer swap at round ${round}` : "Two-team mode"}
        className="inline-flex items-center gap-0.5 text-emerald-700 dark:text-emerald-400"
      >
        <Users className="h-2.5 w-2.5" />
        {typeof round === "number" ? `R${round}` : ""}
      </span>
    );
  }
  return badges;
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

/** The detail line under a run's start time: how long it ran, and what it cost.
 *  Null when the run recorded neither. */
function resolveRunDetailLine(run: RunSummary): string | null {
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
  return parts.join(" / ");
}

function RunRowComponent({
  run,
  showTopBorder,
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
  const borderClass = showTopBorder ? "border-t border-border" : "";
  const badges = buildStatusBadges(run);
  const totalRound = run.scenario_config?.round_count;
  const detailLine = resolveRunDetailLine(run);
  const runDirName = splitRunId(run.run_id).run_dir_name;

  return (
    <>
      <tr
        className={`group cursor-pointer transition-colors hover:bg-accent/50 ${bgClass} ${borderClass}`}
        onClick={handleRowClick}
      >
        {picking ? (
          <td className="w-8 py-2 pl-4 align-middle" onClick={e => e.stopPropagation()}>
            <input
              type="checkbox"
              aria-label={`Select ${run.run_id}`}
              checked={selected}
              onChange={() => onToggleSelected(run.run_id)}
              className="rounded border-input"
            />
          </td>
        ) : null}
        <td className={cn("whitespace-nowrap py-2 font-medium", picking ? "pr-3" : "pl-4 pr-3")}>
          {humanize(run.scenario_name)}
        </td>
        <td className="whitespace-nowrap px-3 py-2 text-left align-middle">
          <div className="inline-flex flex-col items-center gap-0">
            <span className="text-xs font-medium text-muted-foreground">
              {formatTime(run.timestamp)}
            </span>
            {detailLine !== null ? (
              <span className="font-mono text-[10px] text-muted-foreground">{detailLine}</span>
            ) : null}
          </div>
        </td>
        <td className="whitespace-nowrap px-3 py-2 text-right align-middle">
          <div className="inline-flex flex-col items-end gap-0">
            <span
              className={`text-xs font-medium ${
                run.status === "in_progress"
                  ? "text-green-600 dark:text-green-400"
                  : run.status === "error"
                    ? "text-destructive"
                    : "text-muted-foreground"
              }`}
            >
              {STATUS_LABELS[run.status] ?? run.status}
            </span>
            {run.current_round > 0 || badges.length > 0 ? (
              <div className="flex items-center justify-end gap-2 font-mono text-[10px] text-muted-foreground">
                {badges.length > 0 ? (
                  <span className="inline-flex items-center gap-2">{badges}</span>
                ) : null}
                {run.current_round > 0 ? (
                  typeof totalRound === "number" ? (
                    <span>{`Round ${run.current_round} / ${totalRound}`}</span>
                  ) : (
                    <span>{`Round ${run.current_round}`}</span>
                  )
                ) : null}
              </div>
            ) : null}
          </div>
        </td>
        <td className="w-16 py-2 pr-4 text-right">
          <span className="inline-flex items-center gap-1">
            {run.status === "in_progress" ? (
              <span className="group/stop relative">
                <button
                  aria-label="Stop simulation"
                  className="rounded p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                  onClick={e => {
                    e.stopPropagation();
                    onStop(run.run_id);
                  }}
                >
                  <Sword className="h-3.5 w-3.5" />
                </button>
                <span className="pointer-events-none absolute left-1/2 top-full z-50 mt-1 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg group-hover/stop:block">
                  Stop simulation
                </span>
              </span>
            ) : null}
            <span className="group/export relative">
              <button
                aria-label="Export bundle"
                className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                onClick={e => {
                  e.stopPropagation();
                  void downloadAuthenticatedFile({
                    path: `/api/g/{group_slug}/runs/${run.run_id}/export/zip`,
                    searchParams: new URLSearchParams(),
                    fallbackFilename: `${splitRunId(run.run_id).run_dir_name}.zip`,
                  });
                }}
              >
                <Package className="h-3.5 w-3.5" />
              </button>
              <span className="pointer-events-none absolute right-0 top-full z-50 mt-1 hidden whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg group-hover/export:block">
                Export bundle
              </span>
            </span>
            <span className="group/delete relative">
              <button
                aria-label="Delete run"
                className="rounded p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                onClick={e => {
                  e.stopPropagation();
                  onDelete(run.run_id);
                }}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
              <span className="pointer-events-none absolute right-0 top-full z-50 mt-1 hidden whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg group-hover/delete:block">
                Delete run
              </span>
            </span>
          </span>
        </td>
      </tr>
      <tr
        className={`cursor-pointer transition-colors hover:bg-accent/50 ${bgClass}`}
        onClick={handleRowClick}
      >
        <td colSpan={picking ? 5 : 4} className="pb-2 pl-4 pr-4">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="inline-flex items-center gap-1">
              <span className="font-mono text-[10px] text-muted-foreground">{runDirName}</span>
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
                {copied ? (
                  <Check className="h-3 w-3 text-green-500" />
                ) : (
                  <Copy className="h-3 w-3" />
                )}
              </button>
            </span>
            {run.fork_source ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-violet-100 px-1.5 py-0.5 text-[10px] font-medium text-violet-700 dark:bg-violet-900/30 dark:text-violet-400">
                <GitFork className="h-2.5 w-2.5" />
                Fork
              </span>
            ) : null}
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
            {shownKnobs.map(knob => {
              const config = run.scenario_config ?? {};
              if (!(knob in config)) {
                return null;
              }
              return (
                <span
                  key={knob}
                  className="inline-flex items-center gap-1 rounded border border-border bg-muted/50 px-1.5 py-0 text-[11px]"
                >
                  <span className="text-muted-foreground">{humanize(knob)}</span>
                  <span className="font-medium tabular-nums">
                    {formatConfigValue(config[knob])}
                  </span>
                </span>
              );
            })}
            {run.scenario_config && Object.keys(run.scenario_config).length > 0 ? (
              <span onClick={e => e.stopPropagation()}>
                <RunKnobsDropdown
                  scenarioConfig={run.scenario_config}
                  align="left"
                  onOpenValue={(key, value) => onConfigPreview({ key, value })}
                />
              </span>
            ) : null}
            <LabelBadges
              labels={run.labels.filter(label => !label.startsWith("eval:"))}
              size="sm"
            />
            {run.has_evaluation ? (
              <span className="ml-auto inline-flex">
                <EvaluationBadge runId={run.run_id} />
              </span>
            ) : null}
          </div>
        </td>
      </tr>
    </>
  );
}

/**
 * Column widths shared by every day group's table. Each group renders its own
 * ``<table>``, so under automatic layout the widths come from that group's own
 * content and the groups do not line up with each other. Fixed layout plus
 * these widths makes every group agree.
 */
export function RunTableColumns({ picking }: { picking: boolean }) {
  return (
    <colgroup>
      {picking ? <col className="w-8" /> : null}
      <col />
      <col className="w-40" />
      <col className="w-48" />
      <col className="w-24" />
    </colgroup>
  );
}

export const RunRow = memo(RunRowComponent);
