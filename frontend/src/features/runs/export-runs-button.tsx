"use client";

import { Download } from "lucide-react";
import { ExportRunsModal } from "./export-runs-modal";
import { useRunExportSelection } from "./run-export-selection-context";

/**
 * The toolbar's Export button, and the modal it opens.
 *
 * Open state lives in the selection context because the picking bar in the list
 * reopens the modal once runs have been checked, and the two are far apart in the
 * tree.
 */
export function ExportRunsButton({ className }: { className: string }) {
  const { exportOpen, openExport, closeExport, selectedRunIds, picking } = useRunExportSelection();
  const count = picking ? selectedRunIds.size : 0;

  return (
    <>
      <button type="button" onClick={openExport} className={className}>
        <Download className="h-4 w-4" />
        {count > 0 ? `Export (${count})` : "Export"}
      </button>
      {exportOpen ? <ExportRunsModal onClose={closeExport} /> : null}
    </>
  );
}
