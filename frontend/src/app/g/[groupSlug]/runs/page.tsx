"use client";

import { useRef, useState } from "react";
import { GitFork, Plug, Plus, Upload } from "lucide-react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { McpConfigModal } from "@/features/mcp-config/mcp-config-modal";
import { RunList } from "@/features/runs/run-list";
import { API_URL } from "@/shared/lib/api-client";
import { useActiveGroupSlug, useGroupPath } from "@/features/auth/group-context";

export default function RunsPage() {
  const groupPath = useGroupPath();
  const groupSlug = useActiveGroupSlug();
  const [showMcpConfig, setShowMcpConfig] = useState(false);
  const [importProgress, setImportProgress] = useState<{ current: number; total: number } | null>(
    null
  );
  const fileInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    if (files.length === 0) return;
    const failures: string[] = [];
    try {
      for (const [index, file] of files.entries()) {
        setImportProgress({ current: index + 1, total: files.length });
        const formData = new FormData();
        formData.append("file", file);
        try {
          // eslint-disable-next-line no-restricted-globals -- multipart file upload not supported by openapi-fetch
          const resp = await fetch(`${API_URL}/api/g/${groupSlug}/runs/import`, {
            method: "POST",
            body: formData,
          });
          if (!resp.ok) {
            const err = await resp.json();
            failures.push(`${file.name}: ${err.detail}`);
          }
        } catch (err) {
          failures.push(`${file.name}: ${err instanceof Error ? err.message : String(err)}`);
        }
      }
      if (failures.length > 0) {
        alert(`Import failed for ${failures.length} file(s):\n\n${failures.join("\n")}`);
      }
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    } finally {
      setImportProgress(null);
      e.target.value = "";
    }
  };

  const importing = importProgress !== null;
  const importLabel = importProgress
    ? `Importing ${importProgress.current}/${importProgress.total}...`
    : "Import";

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <div className="mb-8 flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">Simulation Runs</h1>
        <div className="flex items-center gap-2">
          <Link
            href={groupPath("/runs/new")}
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90"
          >
            <Plus className="h-4 w-4" />
            Start New Simulation
          </Link>
          <Link
            href={groupPath("/branches")}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <GitFork className="h-4 w-4" />
            Branches
          </Link>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={importing}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
          >
            <Upload className="h-4 w-4" />
            {importLabel}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".tar.gz,.tgz,.gz,application/gzip,application/x-gzip,application/x-tar"
            className="hidden"
            onChange={handleImport}
          />
          <button
            onClick={() => setShowMcpConfig(true)}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Plug className="h-4 w-4" />
            MCP
          </button>
        </div>
      </div>
      <RunList />
      {showMcpConfig && <McpConfigModal onClose={() => setShowMcpConfig(false)} />}
    </main>
  );
}
