"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle } from "lucide-react";
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

      {/* Derived flags */}
      {evaluation.right_answer_wrong_reasons !== null ? (
        <>
          <div className="h-px bg-border" />
          <div>
            <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Flags
            </div>
            {evaluation.right_answer_wrong_reasons ? (
              <div className="flex items-start gap-2 rounded-md bg-amber-50 p-2.5 dark:bg-amber-900/20">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-700 dark:text-amber-400" />
                <div>
                  <div className="text-xs font-medium text-amber-800 dark:text-amber-300">
                    Right answer, wrong reasons
                  </div>
                  <div className="text-[11px] text-amber-700 dark:text-amber-400">
                    The group reached the correct decision but not all private facts were surfaced.
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex items-start gap-2 rounded-md bg-green-50 p-2.5 dark:bg-green-900/20">
                <CheckCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-green-700 dark:text-green-400" />
                <div>
                  <div className="text-xs font-medium text-green-800 dark:text-green-300">
                    Sound reasoning
                  </div>
                  <div className="text-[11px] text-green-700 dark:text-green-400">
                    The group reached the correct decision with proper reasoning.
                  </div>
                </div>
              </div>
            )}
          </div>
        </>
      ) : null}

      {expandedMetric ? (
        <EvidenceModal metric={expandedMetric} onClose={() => setExpandedMetric(null)} />
      ) : null}
    </div>
  );
}
