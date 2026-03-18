"use client";

import { useEffect } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { ProseMarkdown } from "./prose-markdown";

export function ScenarioDescriptionModal({
  scenarioName,
  description,
  onClose,
}: {
  scenarioName: string;
  description: string;
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
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/50" onClick={onClose}>
      <div className="flex min-h-full items-center justify-center p-4">
        <div
          className="flex w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-border bg-background shadow-xl"
          onClick={e => e.stopPropagation()}
        >
          <div className="flex items-center justify-between border-b border-border px-5 py-2.5">
            <span className="text-sm font-medium">{scenarioName}</span>
            <button
              aria-label="Close"
              className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted"
              onClick={onClose}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="overflow-y-auto px-5 py-3" style={{ maxHeight: "calc(100vh - 6rem)" }}>
            <ProseMarkdown>{description}</ProseMarkdown>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
