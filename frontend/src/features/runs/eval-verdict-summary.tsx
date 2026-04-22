"use client";

import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import type { ComponentType, SVGProps } from "react";

type Verdict = "identified" | "partial" | "fail";

type VerdictStyle = {
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  color: string;
};

const VERDICT_ORDER: Verdict[] = ["identified", "partial", "fail"];

const VERDICT_STYLE: Record<Verdict, VerdictStyle> = {
  identified: {
    icon: CheckCircle2,
    color: "text-emerald-600 dark:text-emerald-400",
  },
  partial: {
    icon: AlertTriangle,
    color: "text-amber-600 dark:text-amber-400",
  },
  fail: {
    icon: XCircle,
    color: "text-rose-600 dark:text-rose-400",
  },
};

const VERDICT_LABEL: Record<Verdict, string> = {
  identified: "Identified",
  partial: "Partial",
  fail: "Fail",
};

function isVerdict(value: string): value is Verdict {
  return value === "identified" || value === "partial" || value === "fail";
}

export type EvalLabel = { evaluator: string; verdict: Verdict; raw: string };

export type EvalVerdictGroup = { verdict: Verdict; evaluators: EvalLabel[] };

/** Split a flat label list into regular labels and eval labels. */
export function partitionLabels(labels: string[]): {
  regularLabels: string[];
  evalLabels: EvalLabel[];
} {
  const regularLabels: string[] = [];
  const evalLabels: EvalLabel[] = [];
  for (const label of labels) {
    if (!label.startsWith("eval:")) {
      regularLabels.push(label);
      continue;
    }
    const lastColon = label.lastIndexOf(":");
    const verdict = label.slice(lastColon + 1);
    const evaluator = label.slice(5, lastColon);
    if (!isVerdict(verdict)) {
      continue;
    }
    evalLabels.push({ evaluator, verdict, raw: label });
  }
  return { regularLabels, evalLabels };
}

/** Group a list of eval labels by verdict, preserving the canonical verdict order. */
export function groupEvalLabels(evalLabels: EvalLabel[]): EvalVerdictGroup[] {
  const byVerdict = new Map<Verdict, EvalLabel[]>();
  for (const entry of [...evalLabels].sort((a, b) => a.evaluator.localeCompare(b.evaluator))) {
    const existing = byVerdict.get(entry.verdict);
    if (existing) {
      existing.push(entry);
    } else {
      byVerdict.set(entry.verdict, [entry]);
    }
  }
  const groups: EvalVerdictGroup[] = [];
  for (const verdict of VERDICT_ORDER) {
    const evaluators = byVerdict.get(verdict);
    if (evaluators) {
      groups.push({ verdict, evaluators });
    }
  }
  return groups;
}

/** Compact, plain-text rendering of eval verdicts — intentionally not pill-shaped. */
export function EvalVerdictSummary({
  labels,
  size,
  containerClassName,
}: {
  labels: string[];
  size: "sm" | "md";
  containerClassName?: string;
}) {
  const { evalLabels } = partitionLabels(labels);
  const groups = groupEvalLabels(evalLabels);
  if (groups.length === 0) {
    return null;
  }
  const textClass = size === "sm" ? "text-[10px]" : "text-[11px]";
  const iconClass = size === "sm" ? "h-3 w-3" : "h-3.5 w-3.5";

  return (
    <div
      className={`flex flex-wrap items-center gap-x-4 gap-y-1 font-mono ${textClass} text-muted-foreground ${containerClassName ?? ""}`}
    >
      <span className="font-semibold uppercase tracking-wider opacity-70">Eval</span>
      {groups.map(group => {
        const style = VERDICT_STYLE[group.verdict];
        const Icon = style.icon;
        return (
          <span key={group.verdict} className="inline-flex items-center gap-1.5">
            <Icon className={`${iconClass} shrink-0 ${style.color}`} strokeWidth={2.25} />
            <span className={`font-semibold ${style.color}`}>{VERDICT_LABEL[group.verdict]}:</span>
            <span className="font-normal text-foreground/80">
              {group.evaluators.map(label => label.evaluator).join(", ")}
            </span>
          </span>
        );
      })}
    </div>
  );
}
