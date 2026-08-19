"use client";

import { Wrench } from "lucide-react";
import { HeaderDropdown } from "./header-dropdown";
import { isScenarioTool, type ToolVisibility } from "./tool-visibility";

function ToolCheckbox({
  toolName,
  checked,
  onToggle,
}: {
  toolName: string;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 rounded px-2 py-0.5 transition-colors select-none hover:bg-muted">
      <input
        type="checkbox"
        checked={checked}
        onChange={onToggle}
        className="h-3 w-3 rounded border-border accent-foreground"
      />
      <span className="font-mono text-[11px] text-foreground">{toolName}</span>
    </label>
  );
}

/**
 * The chat header's "Tools" dropdown: one checkbox per tool called in the run,
 * plus all / none shortcuts.
 *
 * Scenario tools and platform communication tools are listed under their own
 * headings, which is also the split behind the defaults (see
 * ``useToolVisibility``). Renders nothing when the run called no tools.
 */
export function ToolFilterDropdown({ visibility }: { visibility: ToolVisibility }) {
  if (visibility.toolNames.length === 0) {
    return null;
  }

  const scenarioTools = visibility.toolNames.filter(isScenarioTool);
  const platformTools = visibility.toolNames.filter(name => !isScenarioTool(name));

  return (
    <HeaderDropdown
      label="Tools"
      icon={<Wrench className="h-3 w-3" />}
      badge={`${visibility.visibleCount}/${visibility.toolNames.length}`}
      panelClassName="w-max min-w-48 p-2"
    >
      {() => (
        <>
          <div className="flex items-center gap-1 px-1 pb-1.5">
            <button
              type="button"
              onClick={() => visibility.setAll(true)}
              className="rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              All
            </button>
            <button
              type="button"
              onClick={() => visibility.setAll(false)}
              className="rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              None
            </button>
          </div>
          {scenarioTools.length > 0 && platformTools.length > 0 ? (
            <div className="px-2 pt-1 text-[10px] font-semibold tracking-wider text-muted-foreground uppercase">
              Scenario
            </div>
          ) : null}
          {scenarioTools.map(name => (
            <ToolCheckbox
              key={name}
              toolName={name}
              checked={visibility.isVisible(name)}
              onToggle={() => visibility.toggle(name)}
            />
          ))}
          {scenarioTools.length > 0 && platformTools.length > 0 ? (
            <div className="mt-1 px-2 pt-1 text-[10px] font-semibold tracking-wider text-muted-foreground uppercase">
              Communication
            </div>
          ) : null}
          {platformTools.map(name => (
            <ToolCheckbox
              key={name}
              toolName={name}
              checked={visibility.isVisible(name)}
              onToggle={() => visibility.toggle(name)}
            />
          ))}
        </>
      )}
    </HeaderDropdown>
  );
}
