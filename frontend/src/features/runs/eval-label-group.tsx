"use client";

import { labelColor } from "./label-picker-modal";

interface EvalVerdictGroup {
  verdict: string;
  evaluators: string[];
}

function parseEvalLabels(labels: string[]): {
  evalGroups: EvalVerdictGroup[];
  regularLabels: string[];
} {
  const regular: string[] = [];
  const byVerdict = new Map<string, string[]>();

  for (const label of [...labels].sort()) {
    if (!label.startsWith("eval:")) {
      regular.push(label);
      continue;
    }
    const lastColon = label.lastIndexOf(":");
    const verdict = label.slice(lastColon + 1);
    const evaluator = label.slice(5, lastColon);
    const existing = byVerdict.get(verdict);
    if (existing) {
      existing.push(evaluator);
    } else {
      byVerdict.set(verdict, [evaluator]);
    }
  }

  const verdictOrder = ["identified", "partial", "fail"];
  const groups: EvalVerdictGroup[] = [];
  for (const verdict of verdictOrder) {
    const evaluators = byVerdict.get(verdict);
    if (evaluators) {
      groups.push({ verdict, evaluators });
    }
  }

  return { evalGroups: groups, regularLabels: regular };
}

/** Renders labels with eval labels grouped by verdict. */
export function LabelBadges({ labels, size }: { labels: string[]; size: "sm" | "md" }) {
  const { evalGroups, regularLabels } = parseEvalLabels(labels);
  const textClass = size === "sm" ? "text-[10px]" : "text-[11px]";
  const paddingClass = size === "sm" ? "px-1.5 py-0.5" : "px-2 py-0.5";

  return (
    <>
      {regularLabels.map(label => {
        const color = labelColor(label);
        return (
          <span
            key={label}
            className={`inline-flex items-center rounded-full ${paddingClass} ${textClass} font-medium ${color.bg} ${color.text}`}
          >
            {label}
          </span>
        );
      })}
      {evalGroups.map(group => {
        const sampleLabel = `eval:x:${group.verdict}`;
        const color = labelColor(sampleLabel);
        return (
          <span
            key={group.verdict}
            className={`inline-flex items-center gap-1 rounded-full ${paddingClass} ${textClass} font-medium ${color.bg} ${color.text}`}
          >
            <span className="opacity-60">eval</span>
            <span className="font-semibold">{group.verdict}:</span>
            {group.evaluators.join(", ")}
          </span>
        );
      })}
    </>
  );
}
