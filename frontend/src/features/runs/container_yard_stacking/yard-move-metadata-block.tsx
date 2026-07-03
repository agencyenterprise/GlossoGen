/**
 * Container-yard `move_container` verdict block rendered beneath a tool call.
 *
 * Shows the expected vs submitted slot move, the accept/soft-reject/reject
 * verdict, and the individual structural checks. Mounted via the scenario
 * plug-in's `renderToolMetadata` hook, keyed by tool `call_id`.
 */

import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { formatExpectedMove, formatSubmittedMove, moveVerdictLabel } from "./move-verdict";

type ContainerYardMoveMetadata = components["schemas"]["ContainerYardMoveMetadata"];

function ExpectedVsSubmittedRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="font-medium text-muted-foreground">{label}:</span>{" "}
      <span className="whitespace-pre-wrap">{value}</span>
    </div>
  );
}

export function YardMoveMetadataBlock({ metadata }: { metadata: ContainerYardMoveMetadata }) {
  const verdict = moveVerdictLabel(metadata);
  return (
    <div>
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Move Verdict (step {metadata.step_index})
      </div>
      <div className="space-y-1 rounded bg-muted p-2 font-mono text-[10px]">
        <ExpectedVsSubmittedRow label="expected" value={formatExpectedMove(metadata)} />
        <ExpectedVsSubmittedRow label="submitted" value={formatSubmittedMove(metadata)} />
        <div>
          <span className="font-medium text-muted-foreground">verdict:</span>{" "}
          <span className={cn("font-medium", verdict.className)}>{verdict.label}</span>
        </div>
        <div>
          <span className="font-medium text-muted-foreground">checks:</span>{" "}
          <span>
            from_occupied={String(metadata.verdict.from_slot_occupied)}, to_empty=
            {String(metadata.verdict.to_slot_empty)}, from_correct=
            {String(metadata.verdict.from_slot_correct)}, to_correct=
            {String(metadata.verdict.to_slot_correct)}
          </span>
        </div>
        {metadata.explanation !== "" ? (
          <ExpectedVsSubmittedRow label="explanation" value={metadata.explanation} />
        ) : null}
      </div>
    </div>
  );
}
