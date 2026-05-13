"use client";

import type { components } from "@/types/api.gen";

type VeyruRunExtras = components["schemas"]["VeyruRunExtras"];

function isVeyruExtras(extras: unknown): extras is VeyruRunExtras {
  if (typeof extras !== "object" || extras === null) return false;
  const tagged = extras as { scenario_name?: string };
  return tagged.scenario_name === "veyru";
}

interface VeyruRoundDetailPanelProps {
  roundNumber: number;
  extras: unknown;
}

/** Veyru case-detail header rendered at the top of the round-timeline modal. */
export function VeyruRoundDetailPanel({ roundNumber, extras }: VeyruRoundDetailPanelProps) {
  if (!isVeyruExtras(extras)) return null;
  const veyruCase = extras.cases.find(c => c.round_number === roundNumber) ?? null;
  if (veyruCase === null) {
    return null;
  }
  return (
    <div className="mb-5 rounded-lg border border-border bg-muted/40 p-3">
      <div className="mb-1 flex items-baseline gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Case {veyruCase.case_number}
        </span>
        <span className="text-sm font-medium">{veyruCase.failure_name}</span>
        <span className="ml-auto text-[11px] text-muted-foreground">
          budget {veyruCase.time_budget_seconds}s
        </span>
      </div>
      <div className="mb-3 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        <span>
          stellar offset <span className="font-mono">{veyruCase.stellar_reading.offset}</span>
        </span>
        <span>
          face <span className="font-mono">{veyruCase.stellar_reading.starting_face}</span>
        </span>
        <span>
          hold <span className="font-mono">{veyruCase.stellar_reading.hold_duration}s</span>
        </span>
        <span>
          intensity <span className="font-mono">{veyruCase.stellar_reading.intensity_level}</span>
        </span>
      </div>
      <div className="space-y-2">
        {veyruCase.stages.map((stage, idx) => (
          <div
            key={`${stage.motif_name}-${idx}`}
            className="rounded-md border border-border/70 bg-background px-3 py-2 text-xs"
          >
            <div className="mb-1 flex items-center gap-2">
              <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                stage {idx}
              </span>
              <span className="font-medium">{stage.motif_name}</span>
              <span className="text-muted-foreground">→</span>
              <span className="text-muted-foreground">{stage.treatment_motif_name}</span>
            </div>
            <div className="mb-1 text-muted-foreground">
              <span className="text-[10px] uppercase tracking-wide">symptoms</span>{" "}
              {stage.observable_symptoms}
            </div>
            <div className="text-muted-foreground">
              <span className="text-[10px] uppercase tracking-wide">expected</span>{" "}
              {stage.judge_expected_actions}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
