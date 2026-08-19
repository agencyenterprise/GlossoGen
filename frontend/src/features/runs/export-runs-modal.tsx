"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useMutation } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Inbox, ListChecks, Loader2, X } from "lucide-react";
import { downloadAuthenticatedFile } from "@/shared/lib/api-client";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { formatBytes } from "./format";
import { useRunExportSelection, type RunExportFilters } from "./run-export-selection-context";
import { useExportPreview } from "./use-export-preview";

type ExportFrame = components["schemas"]["ExportFrame"];
type ExportValueColumn = components["schemas"]["ExportValueColumn"];
type RunSelection =
  components["schemas"]["FilterRunSelection"] | components["schemas"]["ExplicitRunSelection"];

const FRAME_DESCRIPTIONS: Array<{ frame: ExportFrame; title: string; detail: string }> = [
  { frame: "run_level", title: "run_level.csv", detail: "One row per run" },
  { frame: "round_level", title: "round_level.csv", detail: "One row per run and round" },
  { frame: "agent_level", title: "agent_level.csv", detail: "One row per run and agent" },
  {
    frame: "message_level",
    title: "message_level.csv",
    detail: "One row per message, with its text",
  },
  {
    frame: "injection_level",
    title: "injection_level.csv",
    detail: "One row per round-start briefing an agent was given",
  },
];

const COLUMN_SECTIONS: Array<{ group: string; title: string; empty: string }> = [
  { group: "run_metadata", title: "Run info", empty: "No run columns available." },
  { group: "knob", title: "Knobs", empty: "These runs recorded no configuration." },
  { group: "label", title: "Labels", empty: "No labels of the form key=value on these runs." },
  { group: "agent_identity", title: "Agents", empty: "No agents registered on these runs." },
  { group: "lineage", title: "Lineage", empty: "None of these runs were derived from another." },
];

function SectionHeader({
  title,
  selectedCount,
  totalCount,
  expanded,
  onToggleExpanded,
  onAll,
  onNone,
}: {
  title: string;
  selectedCount: number;
  totalCount: number;
  expanded: boolean;
  onToggleExpanded: () => void;
  onAll: () => void;
  onNone: () => void;
}) {
  return (
    <div className="flex items-center justify-between">
      <button
        type="button"
        onClick={onToggleExpanded}
        className="flex items-center gap-1 text-xs font-medium transition-colors hover:text-muted-foreground"
      >
        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        {title}
      </button>
      <div className="flex items-center gap-2">
        <span className="text-[11px] text-muted-foreground">
          {selectedCount} of {totalCount}
        </span>
        <button
          type="button"
          onClick={onAll}
          className="text-[11px] text-muted-foreground transition-colors hover:text-foreground"
        >
          All
        </button>
        <button
          type="button"
          onClick={onNone}
          className="text-[11px] text-muted-foreground transition-colors hover:text-foreground"
        >
          None
        </button>
      </div>
    </div>
  );
}

function CheckItem({
  label,
  suffix,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  suffix: string | null;
  checked: boolean;
  disabled: boolean;
  onChange: () => void;
}) {
  return (
    <label
      className={cn(
        "flex items-center gap-2 rounded px-1.5 py-1 text-xs transition-colors",
        disabled ? "opacity-60" : "cursor-pointer hover:bg-muted/50"
      )}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={onChange}
        className="shrink-0 rounded border-input"
      />
      <span className="truncate font-mono">{label}</span>
      {suffix ? (
        <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">{suffix}</span>
      ) : null}
    </label>
  );
}

/** A scrolling, optionally searchable check list. Used for each column family. */
function ColumnCheckList({
  columns,
  runCount,
  selectedKeys,
  onToggle,
  emptyMessage,
}: {
  columns: ExportValueColumn[];
  runCount: number;
  selectedKeys: ReadonlySet<string>;
  onToggle: (key: string) => void;
  emptyMessage: string;
}) {
  const [search, setSearch] = useState("");
  const showSearch = columns.length > 12;
  const shown = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (needle.length === 0) return columns;
    return columns.filter(column => column.key.toLowerCase().includes(needle));
  }, [columns, search]);

  if (columns.length === 0) {
    return (
      <div className="rounded-md border border-input p-2 text-[11px] text-muted-foreground">
        {emptyMessage}
      </div>
    );
  }

  return (
    <>
      {showSearch ? (
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Filter columns"
          className="w-full rounded-md border border-input bg-background px-2 py-1 text-xs outline-none focus:border-foreground/30"
        />
      ) : null}
      <div className="max-h-44 overflow-y-auto rounded-md border border-input p-2">
        <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
          {shown.map(column => (
            <CheckItem
              key={column.key}
              label={column.key}
              suffix={
                column.runs_with_value < runCount ? `${column.runs_with_value}/${runCount}` : null
              }
              checked={column.always_included || selectedKeys.has(column.key)}
              disabled={column.always_included}
              onChange={() => onToggle(column.key)}
            />
          ))}
        </div>
      </div>
    </>
  );
}

export function ExportRunsModal({ onClose }: { onClose: () => void }) {
  const { selectedRunIds, filters, matchingRunCount, startPicking } = useRunExportSelection();

  const [tab, setTab] = useState<"csv" | "raw">("csv");
  // Someone who checked rows and then opened this meant those rows.
  const [mode, setMode] = useState<"filters" | "explicit">(
    selectedRunIds.size > 0 ? "explicit" : "filters"
  );
  const [includeLogs, setIncludeLogs] = useState(false);
  const [frames, setFrames] = useState<Set<ExportFrame>>(new Set<ExportFrame>(["run_level"]));
  const [columnKeys, setColumnKeys] = useState<ReadonlySet<string>>(new Set());
  const [metricNames, setMetricNames] = useState<ReadonlySet<string>>(new Set());
  const [repeatRunColumns, setRepeatRunColumns] = useState(true);
  const [includeMetricSummaries, setIncludeMetricSummaries] = useState(false);
  const [seededFrom, setSeededFrom] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [progress, setProgress] = useState<{ received: number; total: number | null } | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const [knownMissing, setKnownMissing] = useState<ReadonlySet<string>>(new Set());

  const selection: RunSelection = useMemo(() => {
    if (mode === "explicit") {
      return { kind: "explicit", run_ids: [...selectedRunIds].filter(id => !knownMissing.has(id)) };
    }
    return { kind: "filters", ...filters };
  }, [mode, selectedRunIds, filters, knownMissing]);

  const {
    data: preview,
    isLoading: previewLoading,
    error: previewError,
  } = useExportPreview({
    selection,
    includeRawSizeEstimate: tab === "raw",
    includeLogs,
    enabled: mode === "filters" || selectedRunIds.size > 0,
  });

  // Guarded render-phase update, the same shape as the defaults below: it fires
  // only while there is a newly-reported missing id, so it converges.
  if (preview !== undefined && preview.missing_run_ids.some(id => !knownMissing.has(id))) {
    const next = new Set(knownMissing);
    preview.missing_run_ids.forEach(id => next.add(id));
    setKnownMissing(next);
  }

  // What is on offer changes with the selection, so the defaults are keyed to the
  // set of keys rather than seeded once.
  const availableSignature = useMemo(() => {
    if (preview === undefined) return null;
    return JSON.stringify([
      preview.columns.map(column => column.key),
      preview.metrics.map(metric => metric.metric_name),
    ]);
  }, [preview]);

  // Everything is checked by default: the ask is "all knobs, all evaluators", so
  // the picker is for trimming rather than for opting in.
  if (preview !== undefined && availableSignature !== null && availableSignature !== seededFrom) {
    setColumnKeys(new Set(preview.columns.map(column => column.key)));
    setMetricNames(new Set(preview.metrics.map(metric => metric.metric_name)));
    setSeededFrom(availableSignature);
  }

  const toggleExpanded = (group: string) => {
    const next = new Set(expanded);
    if (next.has(group)) {
      next.delete(group);
    } else {
      next.add(group);
    }
    setExpanded(next);
  };

  const toggle = (
    set: ReadonlySet<string>,
    apply: (next: ReadonlySet<string>) => void,
    key: string
  ) => {
    const next = new Set(set);
    if (next.has(key)) {
      next.delete(key);
    } else {
      next.add(key);
    }
    apply(next);
  };

  const toggleFrame = (frame: ExportFrame) => {
    const next = new Set(frames);
    if (next.has(frame)) {
      next.delete(frame);
    } else {
      next.add(frame);
    }
    setFrames(next);
  };

  const runCount = preview?.run_count ?? 0;
  const overRunCap = preview !== undefined && runCount > preview.max_run_count;
  const rawEstimate = preview?.raw_bytes_estimate ?? null;
  const overRawCap =
    preview !== undefined && rawEstimate !== null && rawEstimate > preview.max_raw_bytes;

  // Every metric is a column, so the round rows they fall on are shared. One
  // metric's rounds are almost always a subset of another's rather than
  // disjoint, which makes the largest the estimate and the sum badly wrong.
  const roundRowsSelected = useMemo(() => {
    if (preview === undefined) return 0;
    return preview.metrics
      .filter(metric => metricNames.has(metric.metric_name))
      .reduce((most, metric) => Math.max(most, metric.rounds_reported), 0);
  }, [preview, metricNames]);

  const agentRows = preview?.agent_row_count ?? 0;
  const messageRows = preview?.message_row_count ?? 0;
  const injectionRows = preview?.injection_row_estimate ?? 0;

  const exportMutation = useMutation({
    mutationFn: async () => {
      setProgress(null);
      const onProgress = (received: number, total: number | null) =>
        setProgress({ received, total });

      if (tab === "raw") {
        const body: components["schemas"]["RawExportRequest"] = {
          selection,
          include_logs: includeLogs,
        };
        await downloadAuthenticatedFile({
          path: "/api/g/{group_slug}/runs/export/raw",
          searchParams: new URLSearchParams(),
          fallbackFilename: "glossogen_runs.zip",
          method: "POST",
          jsonBody: body,
          onProgress,
        });
        return;
      }

      const frameList = enabledFrames;
      const body: components["schemas"]["CsvExportRequest"] = {
        selection,
        frames: frameList,
        columns: [...columnKeys],
        metrics: [...metricNames],
        repeat_run_columns: repeatRunColumns,
        include_metric_summaries: includeMetricSummaries,
      };
      await downloadAuthenticatedFile({
        path: "/api/g/{group_slug}/runs/export/csv",
        searchParams: new URLSearchParams(),
        fallbackFilename: frameList.length > 1 ? "glossogen_csv.zip" : `${frameList[0]}.csv`,
        method: "POST",
        jsonBody: body,
        onProgress,
      });
    },
    onSuccess: onClose,
  });

  // A table nothing would fill is offered as disabled with the reason, rather
  // than silently downloading a header. The agent table is keyed on the roster,
  // so it has rows whenever the runs registered agents, metrics or not.
  const frameDisabledReason = (frame: ExportFrame): string | null => {
    if (frame === "round_level" && roundRowsSelected === 0) {
      return "the selected metrics report no rounds";
    }
    if (frame === "message_level" && messageRows === 0) {
      return "these runs sent no messages";
    }
    if (frame === "injection_level" && injectionRows === 0) {
      return "these runs reached no rounds";
    }
    return null;
  };

  const frameEnabled = (frame: ExportFrame): boolean => frameDisabledReason(frame) === null;

  const enabledFrames = [...frames].filter(frameEnabled);
  // The message and injection tables carry their own rows, so neither needs a
  // column nor a metric checked to be worth downloading.
  const csvCanSubmit =
    runCount > 0 &&
    !overRunCap &&
    enabledFrames.length > 0 &&
    (columnKeys.size + metricNames.size > 0 ||
      enabledFrames.includes("message_level") ||
      enabledFrames.includes("injection_level"));

  const canSubmit = tab === "raw" ? runCount > 0 && !overRunCap && !overRawCap : csvCanSubmit;

  const submitLabel = () => {
    if (!exportMutation.isPending) return "Export";
    if (progress === null) return "Preparing...";
    if (progress.total === null) return `Downloading ${formatBytes(progress.received)}`;
    const percent = Math.round((progress.received / progress.total) * 100);
    return `Downloading ${percent}%`;
  };

  const columnsByGroup = (group: string): ExportValueColumn[] => {
    if (preview === undefined) return [];
    return preview.columns.filter(
      column => column.group === group || (group === "run_metadata" && column.group === "identity")
    );
  };

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
      role="presentation"
    >
      <div className="flex max-h-full w-full max-w-3xl justify-center">
        <div
          className="flex max-h-full w-full flex-col overflow-hidden rounded-xl border border-border bg-background shadow-xl"
          onClick={e => e.stopPropagation()}
        >
          <div className="flex shrink-0 items-center justify-between border-b border-border px-5 py-2.5">
            <h2 className="text-sm font-semibold">Export runs</h2>
            <button
              onClick={onClose}
              aria-label="Close"
              className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
            <section className="space-y-1.5">
              <span className="text-xs font-medium">Runs</span>
              <label className="flex cursor-pointer items-start gap-2 text-xs">
                <input
                  type="radio"
                  checked={mode === "filters"}
                  onChange={() => setMode("filters")}
                  className="mt-0.5"
                />
                <span>
                  All runs matching the current filters
                  <span className="ml-1 text-muted-foreground">({matchingRunCount})</span>
                  <span className="block text-[11px] text-muted-foreground">
                    {describeFilters(filters)}
                  </span>
                </span>
              </label>
              {selectedRunIds.size > 0 ? (
                <label className="flex cursor-pointer items-start gap-2 text-xs">
                  <input
                    type="radio"
                    checked={mode === "explicit"}
                    onChange={() => setMode("explicit")}
                    className="mt-0.5"
                  />
                  <span>
                    The runs you checked
                    <span className="ml-1 text-muted-foreground">({selectedRunIds.size})</span>
                  </span>
                </label>
              ) : (
                <button
                  type="button"
                  onClick={startPicking}
                  className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
                >
                  <ListChecks className="h-3.5 w-3.5" />
                  Pick runs from the list instead
                </button>
              )}
            </section>

            <div className="flex gap-1 border-b border-border">
              {(["csv", "raw"] as const).map(name => (
                <button
                  key={name}
                  type="button"
                  onClick={() => setTab(name)}
                  className={cn(
                    "-mb-px border-b-2 px-3 py-2 text-xs transition-colors",
                    tab === name
                      ? "border-foreground text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  )}
                >
                  {name === "csv" ? "CSV tables" : "Raw run folders"}
                </button>
              ))}
            </div>

            {previewError ? (
              <p className="text-xs text-red-600 dark:text-red-400">
                {previewError instanceof Error ? previewError.message : "Preview failed"}
              </p>
            ) : null}

            {previewLoading ? (
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                Reading the selection
              </p>
            ) : null}

            {preview !== undefined && preview.run_count === 0 ? (
              <div className="flex flex-col items-center gap-2 py-6 text-xs text-muted-foreground">
                <Inbox className="h-8 w-8" />
                No runs match the current filters
              </div>
            ) : null}

            {preview !== undefined && preview.run_count > 0 && overRunCap ? (
              <ExportNotices
                scenarioNames={preview.scenario_names}
                inProgressCount={preview.in_progress_run_count}
                runsWithoutReport={0}
                missingRunIds={mode === "explicit" ? [...knownMissing] : []}
                overRunCap={overRunCap}
                runCount={runCount}
                maxRunCount={preview.max_run_count}
              />
            ) : null}

            {preview !== undefined && preview.run_count > 0 && !overRunCap ? (
              <>
                <ExportNotices
                  scenarioNames={preview.scenario_names}
                  inProgressCount={preview.in_progress_run_count}
                  runsWithoutReport={preview.runs_without_report.length}
                  missingRunIds={mode === "explicit" ? [...knownMissing] : []}
                  overRunCap={overRunCap}
                  runCount={runCount}
                  maxRunCount={preview.max_run_count}
                />

                {tab === "raw" ? (
                  <section className="space-y-2">
                    <label className="flex cursor-pointer items-center gap-2 text-xs">
                      <input
                        type="checkbox"
                        checked={includeLogs}
                        onChange={() => setIncludeLogs(!includeLogs)}
                        className="rounded border-input"
                      />
                      Include debug and stdout logs
                    </label>
                    <p className="text-[11px] text-muted-foreground">
                      {rawEstimate === null
                        ? "Sizing the run folders."
                        : `About ${formatBytes(rawEstimate)} of run folders${
                            includeLogs ? ", logs included" : ""
                          }, before compression.`}
                    </p>
                    {overRawCap ? (
                      <p className="text-[11px] text-amber-600 dark:text-amber-500">
                        Larger than the {formatBytes(preview.max_raw_bytes)} limit. Narrow the
                        selection.
                      </p>
                    ) : null}
                  </section>
                ) : (
                  <>
                    <section className="space-y-1.5">
                      <span className="text-xs font-medium">Tables</span>
                      {FRAME_DESCRIPTIONS.map(({ frame, title, detail }) => {
                        const disabledReason = frameDisabledReason(frame);
                        const enabled = disabledReason === null;
                        return (
                          <label
                            key={frame}
                            className={cn(
                              "flex items-center gap-2 text-xs",
                              enabled ? "cursor-pointer" : "opacity-60"
                            )}
                          >
                            <input
                              type="checkbox"
                              checked={frames.has(frame) && enabled}
                              disabled={!enabled}
                              onChange={() => toggleFrame(frame)}
                              className="rounded border-input"
                            />
                            <span className="font-mono">{title}</span>
                            <span className="text-muted-foreground">
                              {enabled ? detail : `${detail}, but ${disabledReason}`}
                            </span>
                          </label>
                        );
                      })}
                      <label className="flex cursor-pointer items-center gap-2 pt-1 text-xs">
                        <input
                          type="checkbox"
                          checked={repeatRunColumns}
                          onChange={() => setRepeatRunColumns(!repeatRunColumns)}
                          className="rounded border-input"
                        />
                        Repeat run columns on the round, agent and message tables
                      </label>
                      <label className="flex cursor-pointer items-center gap-2 text-xs">
                        <input
                          type="checkbox"
                          checked={includeMetricSummaries}
                          onChange={() => setIncludeMetricSummaries(!includeMetricSummaries)}
                          className="rounded border-input"
                        />
                        Include each metric&apos;s unit, summary, and per-observation notes
                      </label>
                    </section>

                    {COLUMN_SECTIONS.map(({ group, title, empty }) => {
                      const columns = columnsByGroup(group);
                      const selectable = columns.filter(column => !column.always_included);
                      const selectedCount = selectable.filter(column =>
                        columnKeys.has(column.key)
                      ).length;
                      const open = expanded.has(group);
                      return (
                        <section key={group} className="space-y-1.5">
                          <SectionHeader
                            title={title}
                            selectedCount={selectedCount}
                            totalCount={selectable.length}
                            expanded={open}
                            onToggleExpanded={() => toggleExpanded(group)}
                            onAll={() => {
                              const next = new Set(columnKeys);
                              selectable.forEach(column => next.add(column.key));
                              setColumnKeys(next);
                            }}
                            onNone={() => {
                              const next = new Set(columnKeys);
                              selectable.forEach(column => next.delete(column.key));
                              setColumnKeys(next);
                            }}
                          />
                          {open ? (
                            <ColumnCheckList
                              columns={columns}
                              runCount={runCount}
                              selectedKeys={columnKeys}
                              onToggle={key => toggle(columnKeys, setColumnKeys, key)}
                              emptyMessage={empty}
                            />
                          ) : null}
                        </section>
                      );
                    })}

                    <section className="space-y-1.5">
                      <SectionHeader
                        title="Evaluators"
                        selectedCount={metricNames.size}
                        totalCount={preview.metrics.length}
                        expanded={expanded.has("metrics")}
                        onToggleExpanded={() => toggleExpanded("metrics")}
                        onAll={() =>
                          setMetricNames(new Set(preview.metrics.map(m => m.metric_name)))
                        }
                        onNone={() => setMetricNames(new Set())}
                      />
                      {expanded.has("metrics") ? (
                        preview.metrics.length === 0 ? (
                          <div className="rounded-md border border-input p-2 text-[11px] text-muted-foreground">
                            No evaluation reports in this selection. Run an evaluation to get metric
                            columns.
                          </div>
                        ) : (
                          <div className="max-h-44 overflow-y-auto rounded-md border border-input p-2">
                            <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
                              {preview.metrics.map(metric => (
                                <CheckItem
                                  key={metric.metric_name}
                                  label={metric.metric_name}
                                  suffix={
                                    metric.runs_with_value < runCount
                                      ? `${metric.runs_with_value}/${runCount}`
                                      : null
                                  }
                                  checked={metricNames.has(metric.metric_name)}
                                  disabled={false}
                                  onChange={() =>
                                    toggle(metricNames, setMetricNames, metric.metric_name)
                                  }
                                />
                              ))}
                            </div>
                          </div>
                        )
                      ) : null}
                    </section>

                    <section className="space-y-0.5 rounded-md border border-border bg-muted/30 px-3 py-2">
                      <span className="text-xs font-medium">You will get</span>
                      {frames.has("run_level") ? (
                        <p className="text-[11px] text-muted-foreground">
                          run_level.csv — {runCount} rows
                        </p>
                      ) : null}
                      {frames.has("round_level") && frameEnabled("round_level") ? (
                        <p className="text-[11px] text-muted-foreground">
                          round_level.csv — about {roundRowsSelected} rows
                        </p>
                      ) : null}
                      {frames.has("agent_level") && frameEnabled("agent_level") ? (
                        <p className="text-[11px] text-muted-foreground">
                          agent_level.csv — {agentRows} rows
                        </p>
                      ) : null}
                      {frames.has("message_level") && frameEnabled("message_level") ? (
                        <p className="text-[11px] text-muted-foreground">
                          message_level.csv — about {messageRows} rows, read from every run&apos;s
                          event log
                        </p>
                      ) : null}
                      {frames.has("injection_level") && frameEnabled("injection_level") ? (
                        <p className="text-[11px] text-muted-foreground">
                          injection_level.csv — about {injectionRows} rows, read from every
                          run&apos;s event log
                        </p>
                      ) : null}
                      <p className="text-[11px] text-muted-foreground">
                        {enabledFrames.length > 1
                          ? "Delivered as a zip with a columns.csv legend"
                          : "Delivered as a single CSV"}
                      </p>
                      <p className="text-[11px] text-muted-foreground">
                        Tables over {formatBytes(preview.max_csv_bytes)} are refused. Turning off
                        repeating the run columns is the biggest saving.
                      </p>
                    </section>
                  </>
                )}
              </>
            ) : null}

            {exportMutation.error ? (
              <p className="text-xs text-red-600 dark:text-red-400">
                {exportMutation.error instanceof Error
                  ? exportMutation.error.message
                  : "Export failed"}
              </p>
            ) : null}
          </div>

          <div className="flex shrink-0 items-center justify-end gap-2 border-t border-border px-5 py-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-border px-3 py-1 text-[12px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => exportMutation.mutate()}
              disabled={!canSubmit || exportMutation.isPending}
              className="inline-flex items-center gap-1.5 rounded-md bg-foreground px-3 py-1 text-[12px] font-medium text-background transition-opacity hover:opacity-80 disabled:opacity-50"
            >
              {exportMutation.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
              {submitLabel()}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

function describeFilters(filters: RunExportFilters): string {
  const parts: string[] = [];
  if (filters.scenario.length > 0) parts.push(filters.scenario.join(", "));
  if (filters.labels.length > 0) parts.push(`labels ${filters.labels.join(" + ")}`);
  if (filters.run_id_contains) parts.push(`id contains "${filters.run_id_contains}"`);
  if (parts.length === 0) return "No filters, so every run.";
  return parts.join(" · ");
}

function ExportNotices({
  scenarioNames,
  inProgressCount,
  runsWithoutReport,
  missingRunIds,
  overRunCap,
  runCount,
  maxRunCount,
}: {
  scenarioNames: string[];
  inProgressCount: number;
  runsWithoutReport: number;
  missingRunIds: string[];
  overRunCap: boolean;
  runCount: number;
  maxRunCount: number;
}) {
  return (
    <div className="space-y-1">
      {overRunCap ? (
        <p className="text-[11px] text-amber-600 dark:text-amber-500">
          This selection is {runCount} runs. The limit is {maxRunCount}. Narrow the filters or check
          fewer rows.
        </p>
      ) : null}
      {scenarioNames.length > 1 ? (
        <p className="text-[11px] text-muted-foreground">
          Spans {scenarioNames.join(" and ")}. Knobs that only some scenarios define are blank for
          the others.
        </p>
      ) : null}
      {inProgressCount > 0 ? (
        <p className="text-[11px] text-muted-foreground">
          {inProgressCount} still running. Their rows reflect what has been written so far.
        </p>
      ) : null}
      {runsWithoutReport > 0 ? (
        <p className="text-[11px] text-muted-foreground">
          {runsWithoutReport} have no evaluation report, so their metric cells are empty rather than
          zero.
        </p>
      ) : null}
      {missingRunIds.length > 0 ? (
        <p className="text-[11px] text-amber-600 dark:text-amber-500">
          {missingRunIds.length} checked runs no longer exist and are left out of this export.
        </p>
      ) : null}
    </div>
  );
}
