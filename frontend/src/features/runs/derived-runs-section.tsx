"use client";

import { RotateCcw, UserCog, Users } from "lucide-react";
import Link from "next/link";
import { useGroupPath } from "@/features/auth/group-context";
import type { components } from "@/types/api.gen";
import { EvaluationBadge } from "./evaluation-badge";
import { formatCost, humanize } from "./format";

type DerivedRunReference = components["schemas"]["DerivedRunReference"];
type HeadlineMeasurement = components["schemas"]["HeadlineMeasurement"];
type RunStatus = components["schemas"]["RunStatus"];

const STATUS_LABELS: Record<RunStatus, string> = {
  scenario_complete: "Completed",
  in_progress: "In Progress",
  starting: "Starting",
  error: "Error",
  killed: "Killed",
};

const DEFAULT_OPEN_THRESHOLD = 3;

interface DerivedRunsSectionProps {
  derivedRuns: DerivedRunReference[];
}

export function DerivedRunsSection({ derivedRuns }: DerivedRunsSectionProps) {
  if (derivedRuns.length === 0) {
    return null;
  }
  return (
    <details
      className="group/derived mb-3 shrink-0 rounded-md border border-border bg-muted/20"
      open={derivedRuns.length <= DEFAULT_OPEN_THRESHOLD}
    >
      <summary className="cursor-pointer list-none px-3 py-1.5 text-[12px] font-medium text-muted-foreground hover:text-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span className="transition-transform group-open/derived:rotate-90">▸</span>
          Derived runs ({derivedRuns.length})
        </span>
      </summary>
      <ul className="divide-y divide-border border-t border-border">
        {derivedRuns.map(child => (
          <DerivedRunRow key={child.run_id} child={child} />
        ))}
      </ul>
    </details>
  );
}

function DerivedRunRow({ child }: { child: DerivedRunReference }) {
  const groupPath = useGroupPath();
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-1.5 text-[12px]">
      <DerivationIcon derivationType={child.derivation_type} />
      <Link
        href={groupPath(`/runs/${child.run_id}`)}
        className="font-mono text-[11px] underline-offset-2 hover:underline"
      >
        {child.run_id}
      </Link>
      <BoundaryText child={child} />
      <ModelSwapText child={child} />
      <ProgressText child={child} />
      <StatusPill status={child.status} />
      <HeadlineScores measurements={child.headline_measurements} />
      {child.has_evaluation && child.headline_measurements.length === 0 ? (
        <EvaluationBadge runId={child.run_id} />
      ) : null}
      {child.total_cost_usd > 0 ? (
        <span className="ml-auto text-[11px] text-muted-foreground">
          {formatCost(child.total_cost_usd)}
        </span>
      ) : null}
    </li>
  );
}

function DerivationIcon({
  derivationType,
}: {
  derivationType: DerivedRunReference["derivation_type"];
}) {
  if (derivationType === "replace_agent") {
    return (
      <span title="Replace-agent derivation">
        <UserCog className="h-3.5 w-3.5 text-muted-foreground" />
      </span>
    );
  }
  if (derivationType === "cross_run_replace_agent") {
    return (
      <span title="Cross-run replace-agent derivation">
        <Users className="h-3.5 w-3.5 text-violet-600" />
      </span>
    );
  }
  return (
    <span title="Resume-at-round derivation">
      <RotateCcw className="h-3.5 w-3.5 text-emerald-600" />
    </span>
  );
}

function BoundaryText({ child }: { child: DerivedRunReference }) {
  const after =
    child.rounds_after_swap !== null
      ? child.rounds_after_swap
      : child.rounds_after_resume !== null
        ? child.rounds_after_resume
        : null;
  const suffix = after !== null ? ` (+${after})` : "";
  return (
    <span className="text-muted-foreground">
      @ round <span className="font-medium text-foreground">{child.round_start}</span>
      {suffix}
    </span>
  );
}

function ModelSwapText({ child }: { child: DerivedRunReference }) {
  if (child.derivation_type === "replace_agent") {
    if (child.replaced_agent_id === null || child.replacement_model === null) {
      return null;
    }
    return (
      <span className="text-muted-foreground">
        <span className="font-medium text-foreground">{child.replaced_agent_id}</span>
        {" → "}
        <span className="font-medium text-foreground">{child.replacement_model}</span>
      </span>
    );
  }
  if (child.derivation_type === "cross_run_replace_agent") {
    if (child.replaced_agent_id === null || child.imported_model === null) {
      return null;
    }
    return (
      <span className="text-muted-foreground">
        import <span className="font-medium text-foreground">{child.replaced_agent_id}</span>
        {" ← "}
        <span className="font-medium text-foreground">{child.imported_model}</span>
      </span>
    );
  }
  return null;
}

function ProgressText({ child }: { child: DerivedRunReference }) {
  if (child.target_round_count !== null) {
    return (
      <span className="text-muted-foreground">
        {child.current_round} / {child.target_round_count} rounds
      </span>
    );
  }
  if (child.current_round > 0) {
    return <span className="text-muted-foreground">{child.current_round} rounds</span>;
  }
  return null;
}

function StatusPill({ status }: { status: RunStatus }) {
  const label = STATUS_LABELS[status] ?? status;
  const tone =
    status === "in_progress"
      ? "bg-green-100 text-green-700 dark:bg-green-950/40 dark:text-green-300"
      : status === "error"
        ? "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-300"
        : status === "killed"
          ? "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300"
          : status === "starting"
            ? "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300"
            : "bg-muted text-muted-foreground";
  return (
    <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${tone}`}>{label}</span>
  );
}

function HeadlineScores({ measurements }: { measurements: HeadlineMeasurement[] }) {
  if (measurements.length === 0) {
    return null;
  }
  return (
    <span className="inline-flex flex-wrap gap-1">
      {measurements.map((m, index) => (
        <span
          key={`${m.metric_name}::${index}`}
          title={m.summary}
          className="inline-flex items-baseline gap-1 rounded border border-border bg-background px-1.5 py-0.5 text-[10px]"
        >
          <span className="text-muted-foreground">{humanize(m.metric_name)}</span>
          <span className="font-mono font-medium">{m.score.toFixed(2)}</span>
          {m.score_unit !== "" ? (
            <span className="text-[9px] text-muted-foreground">{m.score_unit}</span>
          ) : null}
        </span>
      ))}
    </span>
  );
}
