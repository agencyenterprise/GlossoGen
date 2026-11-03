"use client";

import { Modal } from "@/shared/components/ui/modal";
import { humanize } from "./format";

export function ConfigValueModal({
  configKey,
  value,
  onClose,
}: {
  configKey: string;
  value: string;
  onClose: () => void;
}) {
  return (
    <Modal
      label={humanize(configKey)}
      width="sm"
      panelClassName="p-3"
      panelId={null}
      onClose={onClose}
    >
      <p className="text-xs font-medium">{humanize(configKey)}</p>
      <pre className="mt-2 max-h-40 overflow-auto rounded border border-border bg-muted/40 p-2 text-[11px] whitespace-pre-wrap break-all">
        {value}
      </pre>
      <div className="mt-3 flex justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-border px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          Close
        </button>
      </div>
    </Modal>
  );
}
