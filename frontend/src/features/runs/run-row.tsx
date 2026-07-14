"use client";

import { memo, type MouseEvent, type ReactNode } from "react";
import {
  GitFork,
  HelpCircle,
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
import { splitRunId } from "@/shared/lib/run-id";
import type { components } from "@/types/api.gen";
import {
  elapsedSince,
  formatConfigValue,
  formatConfigValueFull,
  formatCost,
  formatDuration,
  formatTime,
  humanize,
  sortConfigEntries,
} from "./format";
import { CollapsibleConfigBadges } from "./collapsible-config-badges";
import { LabelBadges } from "./eval-label-group";
import { EvaluationBadge } from "./evaluation-badge";

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
  onShowDescription: (run: RunSummary) => void;
  onModelsEnter: (target: HTMLElement, agentModels: RunSummary["agent_models"]) => void;
  onModelsLeave: () => void;
  onStop: (runId: string) => void;
  onDelete: (runId: string) => void;
  onShowNote: (runId: string) => void;
  onConfigPreview: (preview: { key: string; value: string }) => void;
}

function buildStatusBadges(run: RunSummary): ReactNode[] {
  const cfg = run.scenario_config ?? {};
  const badges: ReactNode[] = [];
  if (run.replace_agent_source) {
    badges.push(
      <span
        key="replaced"
        title={`Replaced ${run.replace_agent_source.replaced_agent_id} at round ${run.replace_agent_source.round_start}`}
        className="inline-flex items-center gap-0.5 text-sky-700 dark:text-sky-400"
      >
        <Repeat className="h-2.5 w-2.5" />R{run.replace_agent_source.round_start}
      </span>
    );
  }
  if (run.cross_run_replace_agent_source) {
    const cr = run.cross_run_replace_agent_source;
    badges.push(
      <span
        key="cross-run"
        title={`Cross-run: imported ${cr.replaced_agent_id} from ${cr.source_b_run_id} (through end of round ${cr.source_b_round_end}) at round ${cr.round_start}`}
        className="inline-flex items-center gap-0.5 text-violet-700 dark:text-violet-400"
      >
        <Repeat className="h-2.5 w-2.5" />R{cr.round_start}
      </span>
    );
  }
  if (run.resume_at_round_source) {
    const rr = run.resume_at_round_source;
    badges.push(
      <span
        key="resumed"
        title={`Resumed from start of round ${rr.round_start}, played ${rr.rounds_after_resume} round${rr.rounds_after_resume === 1 ? "" : "s"} after`}
        className="inline-flex items-center gap-0.5 text-emerald-700 dark:text-emerald-400"
      >
        <RotateCcw className="h-2.5 w-2.5" />R{rr.round_start}
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

function RunRowComponent({
  run,
  showTopBorder,
  onNavigate,
  onShowDescription,
  onModelsEnter,
  onModelsLeave,
  onStop,
  onDelete,
  onShowNote,
  onConfigPreview,
}: RunRowProps) {
  const hasBadges =
    run.fork_source ||
    run.has_evaluation ||
    run.labels.length > 0 ||
    run.has_note ||
    (run.scenario_config && Object.keys(run.scenario_config).length > 0);
  const bgClass = run.status === "in_progress" ? "bg-green-50 dark:bg-green-950/20" : "";
  const borderClass = showTopBorder ? "border-t border-border" : "";
  const badges = buildStatusBadges(run);
  const totalRound = run.scenario_config?.round_count;

  return (
    <>
      <tr
        className={`group cursor-pointer transition-colors hover:bg-accent/50 ${bgClass} ${borderClass}`}
        onClick={e => onNavigate(run.run_id, e)}
      >
        <td className="whitespace-nowrap py-2 pl-4 font-medium">
          <span className="inline-flex items-center gap-1.5">
            {humanize(run.scenario_name)}
            <span className="group/help relative">
              <button
                aria-label="Scenario description"
                className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                onClick={e => {
                  e.stopPropagation();
                  onShowDescription(run);
                }}
              >
                <HelpCircle className="h-3.5 w-3.5" />
              </button>
              <span className="pointer-events-none absolute left-1/2 top-full z-50 mt-1 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg group-hover/help:block">
                Scenario description
              </span>
            </span>
          </span>
        </td>
        <td className="max-w-48 px-3 py-2 text-muted-foreground">
          {run.agent_models.length > 0 ? (
            <span
              className="inline-block max-w-full"
              onMouseEnter={e => onModelsEnter(e.currentTarget, run.agent_models)}
              onMouseLeave={onModelsLeave}
            >
              <span className="block truncate">{run.models.join(", ")}</span>
            </span>
          ) : (
            <span className="block truncate" title={run.models.join(", ")}>
              {run.models.join(", ")}
            </span>
          )}
        </td>
        <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-muted-foreground">
          {run.total_messages}
        </td>
        <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-muted-foreground">
          {run.total_cost_usd > 0 ? formatCost(run.total_cost_usd) : "—"}
        </td>
        <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-muted-foreground">
          {run.duration_seconds > 0
            ? formatDuration(run.duration_seconds)
            : run.status === "in_progress"
              ? formatDuration(elapsedSince(run.timestamp))
              : "—"}
        </td>
        <td className="whitespace-nowrap px-3 py-2 text-right text-muted-foreground">
          <div>{formatTime(run.timestamp)}</div>
          <div className="font-mono text-[10px] opacity-60">
            {splitRunId(run.run_id).run_dir_name}
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
                className="rounded p-1 text-muted-foreground opacity-0 transition-all hover:bg-muted hover:text-foreground group-hover:opacity-100"
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
                className="rounded p-1 text-muted-foreground opacity-0 transition-all hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
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
      {hasBadges ? (
        <tr
          className={`cursor-pointer transition-colors hover:bg-accent/50 ${bgClass}`}
          onClick={e => onNavigate(run.run_id, e)}
        >
          <td colSpan={8} className="pb-2 pl-4 pr-4">
            <div className="flex flex-wrap items-center gap-1.5">
              {run.fork_source ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-violet-100 px-1.5 py-0.5 text-[10px] font-medium text-violet-700 dark:bg-violet-900/30 dark:text-violet-400">
                  <GitFork className="h-2.5 w-2.5" />
                  Fork
                </span>
              ) : null}
              {run.has_evaluation ? <EvaluationBadge runId={run.run_id} /> : null}
              <LabelBadges
                labels={run.labels.filter(label => !label.startsWith("eval:"))}
                size="sm"
              />
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
            {run.scenario_config && Object.keys(run.scenario_config).length > 0 ? (
              <CollapsibleConfigBadges
                containerClassName="mt-1"
                entries={sortConfigEntries(Object.entries(run.scenario_config))}
                toggleClassName="inline-flex items-center rounded border border-border bg-muted/50 px-1.5 py-0 text-[11px] text-muted-foreground transition-colors hover:border-primary hover:bg-primary/5"
                renderBadge={([key, value]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={e => {
                      e.stopPropagation();
                      onConfigPreview({ key, value: formatConfigValueFull(value) });
                    }}
                    className="inline-flex max-w-full items-center gap-0.5 rounded border border-border bg-muted/50 px-1.5 py-0 text-[11px] transition-colors hover:border-primary hover:bg-primary/5"
                  >
                    <span className="shrink-0 text-muted-foreground">{humanize(key)}</span>
                    <span className="max-w-48 truncate font-medium">
                      {formatConfigValue(value)}
                    </span>
                  </button>
                )}
              />
            ) : null}
          </td>
        </tr>
      ) : null}
    </>
  );
}

export const RunRow = memo(RunRowComponent);
