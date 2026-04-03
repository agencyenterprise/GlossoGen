"use client";

import { useEffect } from "react";
import { humanize } from "./format";

type ConfigValueModalSecondaryAction = {
  label: string;
  onClick: () => void;
} | null;

export function ConfigValueModal({
  configKey,
  value,
  onClose,
  secondaryAction,
}: {
  configKey: string;
  value: string;
  onClose: () => void;
  secondaryAction: ConfigValueModalSecondaryAction;
}) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-lg border border-border bg-background p-3 shadow-xl"
        onClick={event => event.stopPropagation()}
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
          {secondaryAction ? (
            <button
              type="button"
              onClick={secondaryAction.onClick}
              className="rounded bg-primary px-2 py-1 text-[11px] font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              {secondaryAction.label}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
