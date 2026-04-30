"use client";

import { labelColor } from "./label-picker-modal";

/** Renders labels as colored pill badges. Callers filter out legacy `eval:*` labels before passing them in. */
export function LabelBadges({ labels, size }: { labels: string[]; size: "sm" | "md" }) {
  if (labels.length === 0) {
    return null;
  }
  const textClass = size === "sm" ? "text-[10px]" : "text-[11px]";
  const paddingClass = size === "sm" ? "px-1.5 py-0.5" : "px-2 py-0.5";

  return (
    <>
      {labels.map(label => {
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
