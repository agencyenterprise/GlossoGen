"use client";

import type { components } from "@/types/api.gen";

type OrbitalAnomalyRunExtras = components["schemas"]["OrbitalAnomalyRunExtras"];

function isOrbitalAnomalyExtras(extras: unknown): extras is OrbitalAnomalyRunExtras {
  if (typeof extras !== "object" || extras === null) return false;
  const tagged = extras as { scenario_name?: string };
  return tagged.scenario_name === "orbital_anomaly";
}

interface OrbitalAnomalyRoundDetailPanelProps {
  roundNumber: number;
  extras: unknown;
}

/** Orbital-anomaly case-detail header rendered at the top of the round-timeline modal. */
export function OrbitalAnomalyRoundDetailPanel({
  roundNumber,
  extras,
}: OrbitalAnomalyRoundDetailPanelProps) {
  if (!isOrbitalAnomalyExtras(extras)) return null;
  const anomalyCase = extras.cases.find(c => c.round_number === roundNumber) ?? null;
  if (anomalyCase === null) {
    return null;
  }
  return (
    <div className="mb-5 rounded-lg border border-border bg-muted/40 p-3">
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Anomaly {anomalyCase.case_number}
        </span>
        <span className="ml-auto text-[11px] text-muted-foreground">
          variant <span className="font-mono">{anomalyCase.variant_index}</span>
        </span>
        <span className="text-[11px] text-muted-foreground">
          budget {anomalyCase.time_budget_seconds}s
        </span>
      </div>
      <div className="space-y-2">
        {anomalyCase.stages.map((stage, idx) => (
          <div
            key={`${stage.fault_name}-${idx}`}
            className="rounded-md border border-border/70 bg-background px-3 py-2 text-xs"
          >
            <div className="mb-1 flex items-center gap-2">
              <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                stage {idx}
              </span>
              <span className="font-medium">{stage.fault_name}</span>
              <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                {stage.subsystem}
              </span>
            </div>
            <div className="mb-1 text-muted-foreground">
              <span className="text-[10px] uppercase tracking-wide">cockpit</span>{" "}
              {stage.cockpit_alarm}
            </div>
            <div className="mb-1 text-muted-foreground">
              <span className="text-[10px] uppercase tracking-wide">panel</span>{" "}
              {stage.panel_observation}
            </div>
            <div className="mb-1 text-muted-foreground">
              <span className="text-[10px] uppercase tracking-wide">telemetry</span>{" "}
              {stage.telemetry_readout}
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
