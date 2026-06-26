"use client";

import type { components } from "@/types/api.gen";

type ContainerYardRunExtras = components["schemas"]["ContainerYardRunExtras"];
type ContainerYardContainer = components["schemas"]["ContainerYardContainer"];
type ContainerYardSlot = components["schemas"]["ContainerYardSlot"];

function isYardExtras(extras: unknown): extras is ContainerYardRunExtras {
  if (typeof extras !== "object" || extras === null) return false;
  const tagged = extras as { scenario_name?: string };
  return tagged.scenario_name === "container_yard_stacking";
}

function containerText(container: ContainerYardContainer): string {
  return container.attributes.map(a => a.value).join(", ");
}

function slotStatus(slot: ContainerYardSlot): string {
  return slot.container ? "FULL" : "empty";
}

interface YardRoundDetailPanelProps {
  roundNumber: number;
  extras: unknown;
}

/** Container-yard case-detail header rendered at the top of the round-timeline modal. */
export function YardRoundDetailPanel({ roundNumber, extras }: YardRoundDetailPanelProps) {
  if (!isYardExtras(extras)) return null;
  const yardCase = extras.cases.find(c => c.round_number === roundNumber) ?? null;
  if (yardCase === null) return null;
  return (
    <div className="mb-5 rounded-lg border border-border bg-muted/40 p-3">
      <div className="mb-2 flex items-baseline gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Case {yardCase.case_number}
        </span>
        <span className="text-sm font-medium">
          {yardCase.batch.length} container{yardCase.batch.length === 1 ? "" : "s"}
        </span>
        <span className="ml-auto text-[11px] text-muted-foreground">
          {yardCase.yard_slot_count} slots · budget {yardCase.round_time_budget_seconds}s
        </span>
      </div>

      <div className="mb-3">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
          batch assignment (container · intake → bay)
        </span>
        <div className="mt-1 space-y-0.5 text-[11px] text-muted-foreground">
          {yardCase.batch.map((item, idx) => (
            <div key={idx} className="font-mono">
              {containerText(item.container)} · slot {item.intake_slot} → bay {item.target_slot}
            </div>
          ))}
        </div>
      </div>

      <div>
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
          row occupancy (what the crane sees)
        </span>
        <div className="mt-1 flex flex-wrap gap-1">
          {yardCase.initial_row.map(slot => (
            <span
              key={slot.slot}
              className={
                slot.container
                  ? "rounded border border-border bg-background px-1.5 py-0.5 font-mono text-[10px]"
                  : "rounded border border-dashed border-border/60 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
              }
            >
              {slot.slot}:{slotStatus(slot)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
