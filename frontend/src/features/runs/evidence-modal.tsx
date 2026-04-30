"use client";

import { useEffect } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import type { components } from "@/types/api.gen";
import { humanize } from "./format";
import { ProseMarkdown } from "./prose-markdown";

type MeasurementResponse = components["schemas"]["MeasurementResponse"];

export function EvidenceModal({
  measurement,
  onClose,
}: {
  measurement: MeasurementResponse;
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
            <span className="text-sm font-medium">{humanize(measurement.metric_name)}</span>
            <span className="text-xs text-muted-foreground">
              {measurement.score.toFixed(2)} {measurement.score_unit}
            </span>
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
            Summary
          </div>
          <ProseMarkdown>{measurement.summary}</ProseMarkdown>

          {measurement.per_round.length > 0 ? (
            <>
              <div className="mb-2 mt-5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                Per round
              </div>
              <div className="divide-y divide-border">
                {measurement.per_round.map(observation => (
                  <div
                    key={observation.round_number}
                    className="flex flex-col gap-0.5 py-1.5 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium">Round {observation.round_number}</span>
                      <span className="text-muted-foreground">{observation.value.toFixed(2)}</span>
                    </div>
                    {observation.note ? (
                      <span className="text-muted-foreground">{observation.note}</span>
                    ) : null}
                  </div>
                ))}
              </div>
            </>
          ) : null}

          {measurement.per_agent.length > 0 ? (
            <>
              <div className="mb-2 mt-5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                Per agent
              </div>
              <div className="divide-y divide-border">
                {measurement.per_agent.map(observation => (
                  <div key={observation.agent_id} className="flex flex-col gap-0.5 py-1.5 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{humanize(observation.agent_id)}</span>
                      <span className="text-muted-foreground">{observation.value.toFixed(2)}</span>
                    </div>
                    {observation.note ? (
                      <span className="text-muted-foreground">{observation.note}</span>
                    ) : null}
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
