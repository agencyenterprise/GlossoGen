"use client";

import { SlidersHorizontal } from "lucide-react";
import { formatConfigValue, formatConfigValueFull, humanize, sortConfigEntries } from "./format";
import { HeaderDropdown } from "./header-dropdown";

/**
 * The run header's "Knobs" dropdown: every ``scenario_config`` entry as a
 * key / value row, mode-defining knobs first (see ``sortConfigEntries``).
 *
 * A row whose displayed value is a shortened form of the real one (objects,
 * lists, long strings) is a button that closes the panel and calls
 * ``onOpenValue`` with the full text, so the caller can show it in a modal.
 */
export function RunKnobsDropdown({
  scenarioConfig,
  onOpenValue,
}: {
  scenarioConfig: { [key: string]: unknown };
  onOpenValue: (key: string, value: string) => void;
}) {
  const entries = sortConfigEntries(Object.entries(scenarioConfig));

  return (
    <HeaderDropdown
      label="Knobs"
      icon={<SlidersHorizontal className="h-3 w-3" />}
      badge={String(entries.length)}
      panelClassName="max-h-[60vh] w-max min-w-72 max-w-[min(28rem,80vw)] overflow-y-auto p-2"
    >
      {close => (
        <div className="flex flex-col">
          {entries.map(([key, value]) => {
            const shown = formatConfigValue(value);
            const full = formatConfigValueFull(value);
            if (shown === full) {
              return (
                <div key={key} className="flex items-baseline justify-between gap-6 px-2 py-0.5">
                  <span className="shrink-0 text-muted-foreground">{humanize(key)}</span>
                  <span className="font-medium text-foreground">{shown}</span>
                </div>
              );
            }
            return (
              <button
                key={key}
                type="button"
                title="Show full value"
                onClick={() => {
                  close();
                  onOpenValue(key, full);
                }}
                className="flex items-baseline justify-between gap-6 rounded px-2 py-0.5 text-left transition-colors hover:bg-muted"
              >
                <span className="shrink-0 text-muted-foreground">{humanize(key)}</span>
                <span className="truncate font-medium text-foreground underline decoration-dotted underline-offset-2">
                  {shown}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </HeaderDropdown>
  );
}
