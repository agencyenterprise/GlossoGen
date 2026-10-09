// @vitest-environment jsdom
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useRunDetailData } from "./use-run-detail-data";
import { RunDebugLogs } from "./run-debug-logs";
import { getScenarioPlugin } from "./scenario-registry";

const { get } = vi.hoisted(() => ({
  get: vi.fn<
    (path: string, options?: { signal?: AbortSignal | null }) => Promise<{ data: unknown }>
  >(),
}));
vi.mock("@/shared/lib/api-client", () => ({ api: { GET: get } }));
vi.mock("@/shared/lib/use-event-stream", () => {
  const state = {
    messages: [],
    reasoning: [],
    toolUse: [],
    agents: [],
    channelIds: [],
    debugLogs: [],
    runCycleFailures: [],
    judgeMetadataByCallId: {},
    isConnected: false,
    status: null,
    totalCostUsd: 0,
    durationSeconds: 0,
  };
  return { useEventStream: () => state };
});

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;

beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  container = document.createElement("div");
  root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  get.mockReset();
  get.mockImplementation(async path => ({
    data: path.endsWith("/debug-logs")
      ? { entries: [] }
      : {
          status: "scenario_complete",
          messages: [],
          reasoning: [],
          tool_use: [],
          agents: [],
          channel_ids: [],
          run_cycle_failures: [],
        },
  }));
});

afterEach(async () => {
  await act(async () => root.unmount());
  client.clear();
  container.remove();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function Viewer({ showDebugLogs }: { showDebugLogs: boolean }) {
  const { runId, liveDebugLogs } = useRunDetailData({
    scenario: "incident_commons",
    runDirName: "example",
    scenarioPlugin: getScenarioPlugin("incident_commons"),
    evalJustLaunched: false,
  });
  return showDebugLogs ? createElement(RunDebugLogs, { runId, liveLogs: liveDebugLogs }) : null;
}

async function render(showDebugLogs: boolean) {
  await act(async () => {
    root.render(
      createElement(QueryClientProvider, { client }, createElement(Viewer, { showDebugLogs }))
    );
  });
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 20));
  });
}

it("does not download debug logs until the Logs panel opens", async () => {
  await render(false);
  expect(get.mock.calls.map(call => call[0])).toEqual([
    "/api/g/{group_slug}/runs/{scenario}/{run_dir_name}",
  ]);
  await render(true);
  expect(get.mock.calls.map(call => call[0])).toContain(
    "/api/g/{group_slug}/runs/{scenario}/{run_dir_name}/debug-logs"
  );
});

it("aborts an unfinished snapshot request when leaving the run", async () => {
  let signal: AbortSignal | undefined;
  get.mockImplementation((_path, options) => {
    signal = options?.signal ?? undefined;
    return new Promise(() => {});
  });
  await render(false);
  expect(signal?.aborted).toBe(false);
  await act(async () => root.render(null));
  expect(signal?.aborted).toBe(true);
});

it("releases inactive run snapshots and debug logs after 30 seconds", async () => {
  await render(true);
  vi.useFakeTimers();
  await act(async () => root.render(null));
  expect(client.getQueryData(["run", "incident_commons/example"])).toBeDefined();
  expect(client.getQueryData(["run-debug-logs", "incident_commons/example"])).toBeDefined();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(30_001);
  });
  expect(client.getQueryCache().getAll()).toHaveLength(0);
});

it("shows an empty state when the run has no debug logs", async () => {
  await render(true);
  expect(container.textContent).toContain("No debug logs available for this run.");
});

it("cancels a pending log download when the panel closes", async () => {
  let signal: AbortSignal | undefined;
  await render(false);
  get.mockImplementation((_path, options) => {
    signal = options?.signal ?? undefined;
    return new Promise(() => {});
  });
  await render(true);
  expect(signal?.aborted).toBe(false);
  await render(false);
  expect(signal?.aborted).toBe(true);
});

it("renders an in-progress snapshot already present in the query cache", async () => {
  client.setQueryData(["run", "incident_commons/example"], {
    status: "in_progress",
    messages: [],
    reasoning: [],
    tool_use: [],
    agents: [],
    channel_ids: [],
    run_cycle_failures: [],
  });

  await expect(render(false)).resolves.toBeUndefined();
});
