"use client";

import { partitionLabels } from "./eval-verdict-summary";
import { labelColor } from "./label-picker-modal";

/** Renders regular (non-eval) labels as colored pill badges. Eval verdicts are rendered separately by EvalVerdictSummary. */
export function LabelBadges({ labels, size }: { labels: string[]; size: "sm" | "md" }) {
  const { regularLabels } = partitionLabels(labels);
  if (regularLabels.length === 0) {
    return null;
  }
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
    </>
  );
}
