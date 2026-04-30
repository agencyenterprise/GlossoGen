"use client";

import { useState } from "react";
import { PanelRightClose } from "lucide-react";
import type { components } from "@/types/api.gen";
import { EvidenceModal } from "./evidence-modal";
import { formatCost, humanize } from "./format";

type EvalReportResponse = components["schemas"]["EvalReportResponse"];
type MeasurementResponse = components["schemas"]["MeasurementResponse"];

export function EvalPanel({
  evaluation,
  onClose,
}: {
  evaluation: EvalReportResponse;
  onClose: () => void;
}) {
  const [expandedMeasurement, setExpandedMeasurement] = useState<MeasurementResponse | null>(null);

  return (
    <div className="flex flex-col gap-4 overflow-y-auto border-l border-border p-3.5">
      {/* Metrics */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Metrics
          </span>
          <button
            className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={onClose}
            title="Hide metrics panel"
          >
            <PanelRightClose className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="divide-y divide-border">
          {evaluation.measurements.map(measurement => (
            <button
              key={measurement.metric_name}
              className="flex w-full items-center justify-between gap-2 py-1.5 text-left transition-colors hover:bg-muted/50"
              onClick={() => setExpandedMeasurement(measurement)}
            >
              <span className="truncate text-xs">{humanize(measurement.metric_name)}</span>
              <span className="shrink-0 text-right text-xs text-muted-foreground">
                {measurement.score.toFixed(2)}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Evaluation Cost */}
      {evaluation.evaluation_cost ? (
        <div>
          <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Evaluation Cost
          </div>
          <div className="space-y-1 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Total</span>
              <span className="font-medium">
                {formatCost(evaluation.evaluation_cost.estimated_cost_usd)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Input tokens</span>
              <span className="text-muted-foreground">
                {evaluation.evaluation_cost.input_tokens.toLocaleString()}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Output tokens</span>
              <span className="text-muted-foreground">
                {evaluation.evaluation_cost.output_tokens.toLocaleString()}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Model</span>
              <span className="text-muted-foreground">{evaluation.evaluation_cost.model}</span>
            </div>
          </div>
        </div>
      ) : null}

      {expandedMeasurement ? (
        <EvidenceModal
          measurement={expandedMeasurement}
          onClose={() => setExpandedMeasurement(null)}
        />
      ) : null}
    </div>
  );
}
