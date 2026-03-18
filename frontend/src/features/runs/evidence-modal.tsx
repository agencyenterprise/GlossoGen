"use client";

import { useEffect } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import type { components } from "@/types/api.gen";
import { humanize } from "./format";
import { ProseMarkdown } from "./prose-markdown";
import { VerdictPill } from "./verdict-pill";

type EvalMetricResponse = components["schemas"]["EvalMetricResponse"];

export function EvidenceModal({
  metric,
  onClose,
}: {
  metric: EvalMetricResponse;
  onClose: () => void;
}) {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="mx-4 flex max-h-[80vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-border bg-background shadow-xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">{humanize(metric.evaluator_name)}</span>
            <VerdictPill verdict={metric.verdict} />
            <span className="text-xs text-muted-foreground">{metric.score.toFixed(2)}</span>
          </div>
          <button
            aria-label="Close"
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">
          <div className="mb-3 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Evidence
          </div>
          <ul className="space-y-3">
            {metric.evidence.map(text => (
              <li key={text}>
                <ProseMarkdown>{text}</ProseMarkdown>
              </li>
            ))}
          </ul>

          {Object.keys(metric.per_agent).length > 0 ? (
            <>
              <div className="mb-2 mt-5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                Per agent
              </div>
              <div className="divide-y divide-border">
                {Object.entries(metric.per_agent).map(([agentId, verdict]) => (
                  <div key={agentId} className="flex items-center justify-between py-1.5">
                    <span className="text-xs">{humanize(agentId)}</span>
                    <VerdictPill verdict={verdict} />
                  </div>
                ))}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>,
    document.body
  );
}
