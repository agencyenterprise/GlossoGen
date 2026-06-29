"use client";

import type { components } from "@/types/api.gen";

type DriveModuleRepairRunExtras = components["schemas"]["DriveModuleRepairRunExtras"];
type DriveModuleCaseStageDTO = components["schemas"]["DriveModuleCaseStageDTO"];

function isDriveModuleExtras(extras: unknown): extras is DriveModuleRepairRunExtras {
  if (typeof extras !== "object" || extras === null) return false;
  const tagged = extras as { scenario_name?: string };
  return tagged.scenario_name === "drive_module_repair";
}

interface DriveModuleRepairRoundDetailPanelProps {
  roundNumber: number;
  extras: unknown;
}

/** Group the round's ordered stages by their unit, preserving stage order. */
function stagesByUnit(
  stages: DriveModuleCaseStageDTO[]
): { moduleLabel: string; stages: DriveModuleCaseStageDTO[] }[] {
  const groups: { moduleLabel: string; stages: DriveModuleCaseStageDTO[] }[] = [];
  for (const stage of stages) {
    const last = groups[groups.length - 1];
    if (last !== undefined && last.moduleLabel === stage.module_label) {
      last.stages.push(stage);
    } else {
      groups.push({ moduleLabel: stage.module_label, stages: [stage] });
    }
  }
  return groups;
}

/** Drive-module-repair case-detail header rendered at the top of the round-timeline modal. */
export function DriveModuleRepairRoundDetailPanel({
  roundNumber,
  extras,
}: DriveModuleRepairRoundDetailPanelProps) {
  if (!isDriveModuleExtras(extras)) return null;
  const repairCase = extras.cases.find(c => c.round_number === roundNumber) ?? null;
  if (repairCase === null) {
    return null;
  }
  return (
    <div className="mb-5 rounded-lg border border-border bg-muted/40 p-3">
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Case {repairCase.case_number}
        </span>
        <span className="text-[11px] text-muted-foreground">
          {repairCase.module_count} unit{repairCase.module_count === 1 ? "" : "s"},{" "}
          {repairCase.replacement_count} fault{repairCase.replacement_count === 1 ? "" : "s"}
        </span>
        <span className="ml-auto text-[11px] text-muted-foreground">
          budget {repairCase.round_time_budget_seconds}s
        </span>
      </div>
      <div className="space-y-3">
        {stagesByUnit(repairCase.stages).map(group => (
          <div key={group.moduleLabel}>
            <div className="mb-1 text-[11px] font-medium text-foreground">{group.moduleLabel}</div>
            <div className="space-y-2">
              {group.stages.map(stage => (
                <div
                  key={stage.step_index}
                  className="rounded-md border border-border/70 bg-background px-3 py-2 text-xs"
                >
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                      step {stage.step_index}
                    </span>
                    <span className="text-muted-foreground">{stage.symptom}</span>
                    <span className="text-muted-foreground">→</span>
                    <span className="font-medium">{stage.component}</span>
                    <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {stage.service_class}
                    </span>
                  </div>
                  <ol className="mb-1 list-decimal space-y-0.5 pl-5 text-muted-foreground">
                    {stage.steps.map((step, idx) => (
                      <li key={idx}>{step}</li>
                    ))}
                  </ol>
                  <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-muted-foreground">
                    <span>
                      <span className="text-[10px] uppercase tracking-wide">tool</span>{" "}
                      <span className="font-mono">{stage.tool}</span>
                    </span>
                    <span>
                      <span className="text-[10px] uppercase tracking-wide">torque</span>{" "}
                      <span className="font-mono">{stage.torque_nm} Nm</span>
                    </span>
                    <span>
                      <span className="text-[10px] uppercase tracking-wide">passes</span>{" "}
                      <span className="font-mono">{stage.passes}</span>
                    </span>
                    <span>
                      <span className="text-[10px] uppercase tracking-wide">calibration</span>{" "}
                      <span className="font-mono">{stage.calibration}</span>
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
