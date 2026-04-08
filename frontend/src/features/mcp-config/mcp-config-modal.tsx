"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Check, Copy, X } from "lucide-react";
import { AUTH_STORAGE_KEY } from "@/features/auth/auth-gate";
import { API_URL } from "@/shared/lib/api-client";

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <button
      onClick={handleCopy}
      className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      aria-label="Copy to clipboard"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
}

function CodeBlock({ code }: { code: string }) {
  return (
    <div className="relative">
      <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-md bg-zinc-900 p-3 pr-10 font-mono text-xs text-zinc-100">
        {code}
      </pre>
      <div className="absolute right-2 top-2">
        <CopyButton text={code} />
      </div>
    </div>
  );
}

export function McpConfigModal({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const mcpUrl = `${API_URL}/mcp`;
  const password = typeof window !== "undefined" ? localStorage.getItem(AUTH_STORAGE_KEY) : null;
  const authHeader = password ? `Bearer ${password}` : "Bearer <APP_PASSWORD>";

  const claudeCommand = `claude mcp add-json schmidt-runs '${JSON.stringify({ type: "http", url: mcpUrl, headers: { Authorization: authHeader } })}'`;

  const cursorConfig = JSON.stringify(
    {
      mcpServers: {
        "schmidt-runs": {
          url: mcpUrl,
          headers: {
            Authorization: authHeader,
          },
        },
      },
    },
    null,
    2
  );

  return createPortal(
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/50" onClick={onClose}>
      <div className="flex min-h-full items-center justify-center p-4">
        <div
          className="flex w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-border bg-background shadow-xl"
          onClick={e => e.stopPropagation()}
        >
          <div className="flex items-center justify-between border-b border-border px-5 py-2.5">
            <span className="text-sm font-medium">MCP Integration</span>
            <button
              aria-label="Close"
              className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted"
              onClick={onClose}
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div
            className="overflow-y-auto px-5 py-4 space-y-5"
            style={{ maxHeight: "calc(100vh - 6rem)" }}
          >
            <p className="text-sm text-muted-foreground">
              Connect to browse simulation data and launch runs from Claude Code or Cursor.
              {password
                ? " Your password is pre-filled in the commands below."
                : " Omit the headers object if auth is disabled."}
            </p>

            <div className="space-y-2">
              <h3 className="text-sm font-medium">Claude Code</h3>
              <p className="text-xs text-muted-foreground">Run this command in your terminal:</p>
              <CodeBlock code={claudeCommand} />
            </div>

            <div className="space-y-2">
              <h3 className="text-sm font-medium">Cursor / .cursor/mcp.json</h3>
              <p className="text-xs text-muted-foreground">
                Add this to your{" "}
                <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
                  .cursor/mcp.json
                </code>{" "}
                file:
              </p>
              <CodeBlock code={cursorConfig} />
            </div>

            <div className="space-y-2 border-t border-border pt-4">
              <h3 className="text-sm font-medium">Available Tools</h3>
              <ul className="list-disc pl-5 text-xs text-muted-foreground space-y-1">
                <li>
                  <code className="font-mono">list_scenarios</code> — list available scenarios,
                  models, and providers
                </li>
                <li>
                  <code className="font-mono">list_runs</code> — paginated run listing with
                  filtering by scenario, model, status, fork
                </li>
                <li>
                  <code className="font-mono">get_run_metadata</code> — lightweight run metadata,
                  agents, and evaluation summary
                </li>
                <li>
                  <code className="font-mono">get_run</code> — full run content with messages,
                  reasoning, tool use (opt-in sections)
                </li>
                <li>
                  <code className="font-mono">get_knobs_schema</code> — knobs JSON Schema and
                  available preset files for a scenario
                </li>
                <li>
                  <code className="font-mono">get_knobs_preset</code> — load a scenario knobs preset
                  as a baseline payload
                </li>
                <li>
                  <code className="font-mono">start_run</code> — launch a simulation with scenario,
                  model, provider, and knobs
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
