"use client";

import { useState } from "react";
import type { components } from "@/types/api.gen";
import { EvidenceModal } from "./evidence-modal";
import { humanize } from "./format";
import { VerdictPill } from "./verdict-pill";

type EvalReportResponse = components["schemas"]["EvalReportResponse"];
type EvalMetricResponse = components["schemas"]["EvalMetricResponse"];

export function EvalPanel({ evaluation }: { evaluation: EvalReportResponse }) {
  const [expandedMetric, setExpandedMetric] = useState<EvalMetricResponse | null>(null);

  return (
    <div className="flex flex-col gap-4 overflow-y-auto border-l border-border p-3.5">
      {/* Evaluators */}
      <div>
        <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Evaluators
        </div>
        <div className="divide-y divide-border">
          {evaluation.metrics.map(metric => (
            <button
              key={metric.evaluator_name}
              className="flex w-full items-center justify-between py-1.5 transition-colors hover:bg-muted/50"
              onClick={() => setExpandedMetric(metric)}
            >
              <span className="text-xs">{humanize(metric.evaluator_name)}</span>
              <div className="flex items-center gap-2">
                <span className="min-w-[28px] text-right text-xs text-muted-foreground">
                  {metric.score.toFixed(2)}
                </span>
                <VerdictPill verdict={metric.verdict} />
              </div>
            </button>
          ))}
        </div>
      </div>

      {expandedMetric ? (
        <EvidenceModal metric={expandedMetric} onClose={() => setExpandedMetric(null)} />
      ) : null}
    </div>
  );
}
