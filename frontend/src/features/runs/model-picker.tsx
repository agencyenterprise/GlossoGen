"use client";

import { useMemo, useState } from "react";
import { Check } from "lucide-react";

interface ModelOption {
  model_prefix: string;
  provider: string;
}

interface ProviderGroup {
  provider: string;
  models: ModelOption[];
}

function groupByProvider(models: ModelOption[], filter: string): ProviderGroup[] {
  const lowerFilter = filter.toLowerCase();
  const grouped = new Map<string, ModelOption[]>();

  for (const m of models) {
    const providerMatches = m.provider.toLowerCase().includes(lowerFilter);
    const modelMatches = m.model_prefix.toLowerCase().includes(lowerFilter);

    if (!lowerFilter || providerMatches || modelMatches) {
      const existing = grouped.get(m.provider);
      if (existing) {
        existing.push(m);
      } else {
        grouped.set(m.provider, [m]);
      }
    }
  }

  return Array.from(grouped.entries()).map(([provider, models]) => ({
    provider,
    models,
  }));
}

export function ModelPicker({
  models,
  selectedModel,
  onSelect,
}: {
  models: ModelOption[];
  selectedModel: string;
  onSelect: (model: string, provider: string) => void;
}) {
  const [filter, setFilter] = useState("");

  const groups = useMemo(() => groupByProvider(models, filter), [models, filter]);

  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium">Model</label>
      <input
        type="text"
        placeholder="Filter models..."
        value={filter}
        onChange={e => setFilter(e.target.value)}
        className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm outline-none focus:border-primary"
      />
      <div className="max-h-56 overflow-y-auto rounded-md border border-input">
        {groups.length === 0 ? (
          <p className="px-3 py-2 text-xs text-muted-foreground">No models match your filter.</p>
        ) : (
          groups.map(group => (
            <div key={group.provider}>
              <div className="sticky top-0 bg-muted/80 px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground backdrop-blur-sm">
                {group.provider}
              </div>
              {group.models.map(m => {
                const isSelected = m.model_prefix === selectedModel;
                return (
                  <button
                    key={m.model_prefix}
                    type="button"
                    onClick={() => onSelect(m.model_prefix, m.provider)}
                    className={`flex w-full items-center justify-between px-3 py-1.5 text-left text-sm transition-colors ${
                      isSelected ? "bg-primary/10 font-medium text-primary" : "hover:bg-muted/50"
                    }`}
                  >
                    <span>{m.model_prefix}</span>
                    {isSelected ? <Check className="h-3.5 w-3.5 shrink-0" /> : null}
                  </button>
                );
              })}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
