"use client";

import { X } from "lucide-react";
import { Modal } from "@/shared/components/ui/modal";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";

type ProtocolAgreementReport = components["schemas"]["ProtocolAgreementReport"];
type ProtocolConvention = components["schemas"]["ProtocolConvention"];
type AgreementStep = components["schemas"]["AgreementStep"];

const STAGE_LABEL: Record<AgreementStep["stage"], string> = {
  proposed: "Proposed",
  understood: "Understood",
};

/** Shows how the agents came to share each convention, from the protocol_agreement
 *  metric's sidecar. Each piece of evidence jumps to its message in the chat. */
export function ProtocolAgreementModal({
  report,
  onJumpToMessage,
  onClose,
}: {
  report: ProtocolAgreementReport;
  onJumpToMessage: (messageId: string) => void;
  onClose: () => void;
}) {
  return (
    <Modal
      label="How the agents agreed on a protocol"
      width="2xl"
      panelClassName="flex max-h-[80vh] flex-col overflow-hidden"
      panelId={null}
      onClose={onClose}
    >
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <span className="text-sm font-medium">How the agents agreed on a protocol</span>
        <button
          aria-label="Close"
          className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
        <p className="text-sm text-foreground/90">{report.summary}</p>
        {report.conventions.length === 0 ? (
          <p className="text-xs text-muted-foreground">The judge found no convention.</p>
        ) : null}
        {report.conventions.map((convention, index) => (
          <ConventionCard
            key={`${convention.name}::${index}`}
            convention={convention}
            onJumpToMessage={onJumpToMessage}
          />
        ))}
      </div>
    </Modal>
  );
}

function sharedLabel(convention: ProtocolConvention): string {
  if (!convention.adopted_by_all) {
    return "Not used by every agent";
  }
  if (convention.first_shared_round === null) {
    return "Used by every agent";
  }
  return `Used by every agent from round ${convention.first_shared_round}`;
}

function ConventionCard({
  convention,
  onJumpToMessage,
}: {
  convention: ProtocolConvention;
  onJumpToMessage: (messageId: string) => void;
}) {
  return (
    <section className="rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">{convention.name}</h3>
        <span
          className={cn(
            "rounded px-1.5 py-0.5 text-[10.5px]",
            convention.adopted_by_all
              ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
              : "bg-muted text-muted-foreground"
          )}
        >
          {sharedLabel(convention)}
        </span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{convention.meaning}</p>
      <ol className="mt-3 space-y-3">
        {convention.steps.map((step, index) => (
          <li key={`${step.stage}::${index}`} className="border-l-2 border-border pl-3">
            <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              {STAGE_LABEL[step.stage]} · round {step.round_number} · {step.agent_id}
            </div>
            <p className="mt-0.5 text-xs">{step.explanation}</p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {step.evidence.map(evidence => (
                <button
                  key={evidence.message_id}
                  className="rounded border border-border bg-muted/40 px-1.5 py-0.5 font-mono text-[10.5px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  title={evidence.text}
                  onClick={() => onJumpToMessage(evidence.message_id)}
                >
                  R{evidence.round_number} · {evidence.agent_id}
                </button>
              ))}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
