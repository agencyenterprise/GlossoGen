// @vitest-environment jsdom
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useEventStream } from "./use-event-stream";

vi.mock("./api-client", () => ({
  buildEventStreamUrl: vi.fn(async () => "http://example.test/events"),
}));

type Listener = (event: MessageEvent) => void;

class FakeEventSource {
  static readonly CLOSED = 2;
  static instances: FakeEventSource[] = [];

  readonly listeners = new Map<string, Listener[]>();
  readyState = 1;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(name: string, listener: Listener) {
    const listeners = this.listeners.get(name) ?? [];
    listeners.push(listener);
    this.listeners.set(name, listeners);
  }

  close() {
    this.readyState = FakeEventSource.CLOSED;
  }

  emit(name: string, data: unknown) {
    const event = new MessageEvent(name, { data: JSON.stringify(data) });
    for (const listener of this.listeners.get(name) ?? []) listener(event);
  }
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.stubGlobal("EventSource", FakeEventSource);
  FakeEventSource.instances.length = 0;
  container = document.createElement("div");
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function Viewer({
  runId,
  knownEventIds = new Set(),
}: {
  runId: string;
  knownEventIds?: Set<string>;
}) {
  const state = useEventStream(runId, true, knownEventIds, null);
  return createElement(
    "output",
    null,
    JSON.stringify({
      connected: state.isConnected,
      cost: state.totalCostUsd,
      duration: state.durationSeconds,
      messages: state.messages.length,
      status: state.status,
    })
  );
}

async function render(runId: string, knownEventIds?: Set<string>) {
  await act(async () => {
    root.render(createElement(Viewer, { runId, knownEventIds }));
    await Promise.resolve();
  });
}

it("clears terminal and connection state when the run changes", async () => {
  await render("scenario/first");
  const first = FakeEventSource.instances[0];
  expect(first).toBeDefined();

  await act(async () => {
    first?.onopen?.();
    first?.emit("simulation_ended", {
      event_id: "end-1",
      reason: "scenario_complete",
      total_messages: 4,
      total_cost_usd: 1.25,
      duration_seconds: 9,
    });
  });
  expect(container.textContent).toContain('"cost":1.25');
  expect(container.textContent).toContain('"duration":9');

  await render("scenario/second");

  expect(container.textContent).toBe(
    '{"connected":false,"cost":0,"duration":0,"messages":0,"status":null}'
  );
});

it("deduplicates a message using the message id exposed by the REST snapshot", async () => {
  await render("scenario/run", new Set(["message-1"]));
  const source = FakeEventSource.instances[0];

  await act(async () => {
    source?.emit("message_sent", {
      event_id: "event-1",
      round_number: 1,
      token_count: 2,
      message: {
        message_id: "message-1",
        channel_id: "link",
        sender_agent_id: "agent",
        text: "already in REST",
        timestamp: "2026-10-09T00:00:00Z",
      },
    });
  });

  expect(container.textContent).toContain('"messages":0');
});
