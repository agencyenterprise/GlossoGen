// @vitest-environment jsdom
import { act, createElement, type ComponentProps } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatPane } from "./chat-pane";
import { mergeEntries } from "./display-entry";

vi.mock("@/features/auth/group-context", () => ({ useGroupPath: () => (path: string) => path }));

let container: HTMLDivElement;
let root: Root;
const resizeObservers = new Set<TestResizeObserver>();

class TestResizeObserver {
  targets = new Map<Element, number>();
  constructor(private callback: ResizeObserverCallback) {
    resizeObservers.add(this);
  }
  observe(element: Element) {
    this.targets.set(element, -1);
  }
  unobserve(element: Element) {
    this.targets.delete(element);
  }
  disconnect() {
    resizeObservers.delete(this);
  }
  flush() {
    const entries: ResizeObserverEntry[] = [];
    for (const [target, previousHeight] of this.targets) {
      const height = (target as HTMLElement).offsetHeight;
      if (height === previousHeight) continue;
      this.targets.set(target, height);
      entries.push({
        target,
        contentRect: new DOMRect(0, 0, 800, height),
        borderBoxSize: [{ inlineSize: 800, blockSize: height }],
        contentBoxSize: [{ inlineSize: 800, blockSize: height }],
        devicePixelContentBoxSize: [],
      });
    }
    if (entries.length) this.callback(entries, this);
  }
}

async function settle() {
  for (let i = 0; i < 5; i++) {
    await act(async () => {
      for (const observer of resizeObservers) observer.flush();
      await new Promise(resolve => setTimeout(resolve, 20));
    });
  }
}

function scroller() {
  return container.querySelector<HTMLDivElement>(".overflow-y-auto")!;
}

async function scrollTo(top: number) {
  await act(async () => scroller().scrollTo({ top }));
  await settle();
}

async function clickButton(text: string) {
  const button = [...container.querySelectorAll("button")].find(el =>
    el.textContent?.includes(text)
  );
  expect(button, `button containing ${text}`).toBeDefined();
  await act(async () => button!.click());
  await settle();
}

// jsdom has no layout engine. Supply a fixed viewport and measured row heights
// while running the real React component and TanStack virtualizer.
beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  resizeObservers.clear();
  vi.stubGlobal("ResizeObserver", TestResizeObserver);
  vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockImplementation(function (
    this: HTMLElement
  ) {
    if (this.hasAttribute("data-chat-row")) return Number(this.dataset.testHeight ?? 100);
    return parseFloat(this.style.height) || 600;
  });
  vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(800);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(600);
  vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockImplementation(function (
    this: HTMLElement
  ) {
    return parseFloat((this.firstElementChild as HTMLElement | null)?.style.height ?? "") || 600;
  });
  const offsets = new WeakMap<HTMLElement, number>();
  vi.spyOn(HTMLElement.prototype, "scrollTop", "get").mockImplementation(function (
    this: HTMLElement
  ) {
    return offsets.get(this) ?? 0;
  });
  vi.spyOn(HTMLElement.prototype, "scrollTop", "set").mockImplementation(function (
    this: HTMLElement,
    value: number
  ) {
    const top = Math.max(0, Math.min(value, this.scrollHeight - this.clientHeight));
    if (top === (offsets.get(this) ?? 0)) return;
    offsets.set(this, top);
    queueMicrotask(() => this.dispatchEvent(new Event("scroll")));
  });
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) =>
    window.setTimeout(() => callback(performance.now()), 0)
  );
  vi.stubGlobal("cancelAnimationFrame", (id: number) => window.clearTimeout(id));
  Object.defineProperty(HTMLElement.prototype, "scrollTo", {
    configurable: true,
    value: vi.fn(function (this: HTMLElement, options: ScrollToOptions) {
      this.scrollTop = options.top ?? 0;
    }),
  });
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
    configurable: true,
    value: vi.fn(),
  });
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function props(count: number): ComponentProps<typeof ChatPane> {
  const messages = mergeEntries(
    [],
    [],
    [],
    Array.from({ length: count }, (_, cycle) => ({
      message_id: `failure-${cycle}`,
      agent_id: "member_1",
      timestamp: new Date(1_700_000_000_000 + cycle).toISOString(),
      round_number: cycle < count / 2 ? 1 : 2,
      cycle,
      error_type: "RateLimitError",
      message: "Provider limit reached",
    })),
    {},
    {},
    {}
  );
  return {
    messages,
    agents: [],
    exportSlot: null,
    selectedChannel: null,
    agentColorMap: new Map(),
    channelColorMap: new Map(),
    onSelectAgent: vi.fn(),
    highlightedMessageId: null,
    highlightNonce: 0,
    dividerJumpTarget: null,
    dividerJumpNonce: 0,
    forkPointMessageId: null,
    scenarioMarkers: [],
    replaceAgentSource: null,
    crossRunReplaceAgentSource: null,
    scenarioName: "incident_commons",
    primaryChannelIds: [],
    scenarioExtras: null,
    roundEndings: [],
    roundResults: [],
    roundInjections: [],
    resumeCutoffTimestamp: null,
    agentSwapDividers: [],
    contextCompactionMarkers: [],
    activeInstanceRoundRange: null,
  };
}

async function render(value: ComponentProps<typeof ChatPane>) {
  await act(async () => root.render(createElement(ChatPane, value)));
  await settle();
}

describe("chat virtualization", () => {
  it("mounts a bounded window and can highlight an offscreen entry", async () => {
    const value = props(2000);
    await render(value);
    const mounted = container.querySelectorAll('[data-chat-row="entry"]').length;
    expect(mounted).toBeGreaterThan(0);
    expect(mounted).toBeLessThan(30);
    expect(container.textContent).toContain("retry 1999");
    await render({ ...value, highlightedMessageId: "failure-20", highlightNonce: 1 });
    expect(container.querySelector(".animate-highlight")?.textContent).toContain("retry 20");
    expect(container.querySelectorAll('[data-chat-row="entry"]').length).toBeLessThan(30);
  });

  it("mounts an offscreen round divider before highlighting it", async () => {
    const value = props(2000);
    const swap = {
      agent_id: "member_1",
      role_name: "Member",
      round_number: 1,
      generation: 2,
      old_model: "old",
      new_model: "new",
      post_swap_instance_key: "member_1:2",
    };
    await render({ ...value, agentSwapDividers: [swap] });
    await render({
      ...value,
      agentSwapDividers: [swap],
      dividerJumpTarget: {
        elementId: "agent-swap-divider-r1-member_1",
        roundNumber: 1,
      },
      dividerJumpNonce: 1,
    });
    expect(
      container.querySelector("#agent-swap-divider-r1-member_1.animate-highlight")
    ).not.toBeNull();
  });

  it("repeats the same flash, expires it, and cancels stale highlights", async () => {
    const value = { ...props(20), highlightedMessageId: "failure-12", highlightNonce: 1 };
    await render(value);
    const first = container.querySelector(".animate-highlight")!;
    expect(first.textContent).toContain("retry 12");
    const remove = vi.spyOn(first.classList, "remove");
    await render({ ...value, highlightNonce: 2 });
    expect(remove).toHaveBeenCalledWith("animate-highlight");
    expect(first.classList.contains("animate-highlight")).toBe(true);
    await render({ ...value, highlightedMessageId: "failure-13", highlightNonce: 3 });
    expect(first.classList.contains("animate-highlight")).toBe(false);
    expect(container.querySelectorAll(".animate-highlight")).toHaveLength(1);
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 1550));
    });
    expect(container.querySelector(".animate-highlight")).toBeNull();
  });

  it("follows appended activity only while the reader is at the bottom", async () => {
    const value = props(200);
    await render(value);
    const next = props(201).messages.at(-1)!;
    const appended = { ...value, messages: [...value.messages, next] };
    await render(appended);
    expect(scroller().scrollHeight - scroller().scrollTop - scroller().clientHeight).toBeLessThan(
      80
    );
    expect(container.textContent).toContain("retry 200");

    await scrollTo(1000);
    const before = scroller().scrollTop;
    await render({ ...value, messages: [...appended.messages, props(202).messages.at(-1)!] });
    expect(scroller().scrollTop).toBe(before);
    expect(container.textContent).not.toContain("retry 201");
    await clickButton("Scroll to bottom");
    expect(container.textContent).toContain("retry 201");
  });

  it("remeasures a growing row without pulling a history reader to the bottom", async () => {
    await render(props(200));
    await scrollTo(1000);
    const before = scroller().scrollTop;
    const spacer = scroller().firstElementChild as HTMLElement;
    const height = parseFloat(spacer.style.height);
    const row = container.querySelectorAll<HTMLElement>('[data-chat-row="entry"]')[7]!;
    row.dataset.testHeight = "420";
    await settle();
    expect(parseFloat(spacer.style.height)).toBe(height + 320);
    expect(scroller().scrollTop).toBe(before);
  });

  it("filters channels, reasoning and tools and recovers from an empty view", async () => {
    const value = props(3);
    value.messages = value.messages.map((entry, i) => ({
      ...entry,
      is_run_cycle_failure: false,
      round_number: 1,
      is_reasoning: i === 1,
      is_tool_use: i === 2,
      tool_name: i === 2 ? "inspect_case" : "",
      channel_id: i === 2 ? "" : "team",
      channel_ids: i === 2 ? [] : ["team"],
      text: `content-${i}`,
    }));
    await render(value);
    expect(container.querySelectorAll('[data-chat-row="entry"]')).toHaveLength(3);
    await act(async () =>
      container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click()
    );
    await settle();
    expect(container.textContent).not.toContain("content-1");
    await clickButton("Tools");
    await clickButton("None");
    expect(container.querySelectorAll('[data-chat-row="entry"]')).toHaveLength(1);
    await render({ ...value, selectedChannel: "missing" });
    expect(container.querySelector('[data-chat-row="entry"]')).toBeNull();
    await render({ ...value, selectedChannel: "team" });
    expect(container.textContent).toContain("content-0");
    expect(container.querySelectorAll('[data-chat-row="entry"]')).toHaveLength(1);
  });

  it("documents that expanded details reset after their row is virtualized away", async () => {
    const value = props(200);
    await render({ ...value, highlightedMessageId: "failure-20", highlightNonce: 1 });
    await clickButton("retry 20");
    expect(container.querySelector("pre")?.textContent).toContain("Provider limit reached");
    await scrollTo(scroller().scrollHeight);
    expect(container.textContent).not.toContain("retry 20");
    await render({ ...value, highlightedMessageId: "failure-20", highlightNonce: 2 });
    expect(container.textContent).toContain("retry 20");
    expect(container.querySelector("pre")).toBeNull();
  });

  it("shows a short briefing preview and renders the full Markdown on expansion", async () => {
    const value = props(1);
    const text = "Preview " + "x".repeat(350) + "\n\n**Full briefing tail**";
    value.roundInjections = [
      { round_number: 1, agent_id: "member_1", text, timestamp: value.messages[0]!.timestamp },
    ];
    await render(value);
    expect(container.textContent).not.toContain("Full briefing tail");
    await clickButton("Injection");
    expect(container.querySelector("strong")?.textContent).toBe("Full briefing tail");
    await clickButton("Injection");
    expect(container.querySelector("strong")).toBeNull();
  });

  it("offers the full briefing when the preview cuts it and keeps its lines apart", async () => {
    const value = props(1);
    const text =
      "Round 1. TEAM TASK\nAll crafters got this.\n\nALL RECIPES\ncraft 1 a using 1 b\ncraft 1 c using 1 d";
    value.roundInjections = [
      { round_number: 1, agent_id: "member_1", text, timestamp: value.messages[0]!.timestamp },
    ];
    await render(value);
    await clickButton("Show full briefing");
    const recipes = [...container.querySelectorAll("p")].find(el =>
      el.textContent?.startsWith("ALL RECIPES")
    );
    expect(recipes?.textContent).toBe("ALL RECIPES\ncraft 1 a using 1 b\ncraft 1 c using 1 d");
    expect(recipes?.closest("[class*='whitespace-pre-line']")).not.toBeNull();
    expect(container.textContent).not.toContain("Show full briefing");
  });

  it("offers no expansion for a briefing the preview already shows whole", async () => {
    const value = props(1);
    value.roundInjections = [
      {
        round_number: 1,
        agent_id: "member_1",
        text: "Round 2 begins.",
        timestamp: value.messages[0]!.timestamp,
      },
    ];
    await render(value);
    expect(container.textContent).toContain("Round 2 begins.");
    expect(container.textContent).not.toContain("Show full briefing");
  });
});
