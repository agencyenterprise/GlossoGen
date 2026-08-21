"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus, SlidersHorizontal, XCircle } from "lucide-react";
import { api } from "@/shared/lib/api-client";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { humanize } from "./format";
import { describeKnobFilter } from "./knob-filter-encoding";

type FilterableKnob = components["schemas"]["FilterableKnob"];
type FilterableKnobType = components["schemas"]["FilterableKnobType"];

const ORDERED_OPERATORS = [">=", "<=", ">", "<", "=", "!="] as const;
const EQUALITY_OPERATORS = ["=", "!="] as const;

/** Which operators a knob's type can express. A boolean takes only equality,
 *  and only against true or false, so it needs no negation either. */
function operatorsFor(knobType: FilterableKnobType): readonly string[] {
  if (knobType === "integer" || knobType === "number") {
    return ORDERED_OPERATORS;
  }
  if (knobType === "boolean") {
    return ["="];
  }
  return EQUALITY_OPERATORS;
}

function FilterChip({ raw, onRemove }: { raw: string; onRemove: () => void }) {
  const label = describeKnobFilter(raw);
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-primary/15 px-2 py-0.5 text-[11px] font-medium text-primary ring-1 ring-primary/30">
      <span className="font-mono">{label}</span>
      <button
        type="button"
        aria-label={`Remove filter ${label}`}
        onClick={onRemove}
        className="transition-opacity hover:opacity-70"
      >
        <XCircle className="h-3 w-3" />
      </button>
    </span>
  );
}

// What the backend reads as "this knob is not set". `_NULL_TEXT` in
// glossogen/knob_filter.py accepts several spellings; this is the one to emit.
const NOT_SET_VALUE = "null";

const SELECT_CLASS =
  "rounded-md border border-border bg-background px-1.5 py-0.5 text-[11px] text-foreground focus:border-primary focus:outline-none";

/**
 * Builds knob conditions against the selected scenario's knobs schema and shows
 * the applied ones as removable chips.
 *
 * The scenario decides which knobs exist, so this renders for one scenario at a
 * time. Each condition is encoded as ``<knob><operator><value>``, which is what
 * the runs endpoint's repeatable ``knob`` parameter takes.
 */
export function KnobFilterBar({
  scenarioName,
  filters,
  onChange,
}: {
  scenarioName: string;
  filters: string[];
  onChange: (filters: string[]) => void;
}) {
  const [knobName, setKnobName] = useState("");
  const [operator, setOperator] = useState("");
  const [value, setValue] = useState("");

  const { data } = useQuery({
    queryKey: ["filterable-knobs", scenarioName],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/g/{group_slug}/scenarios/{scenario_name}/filterable-knobs",
        { params: { path: { scenario_name: scenarioName } } }
      );
      if (error) {
        throw new Error("Failed to fetch filterable knobs");
      }
      return data;
    },
    staleTime: 5 * 60_000,
  });

  // The endpoint answers in the knobs model's declaration order, which groups
  // related knobs but leaves no way to find one by name in a list this long.
  // The picker sorts by the label it shows.
  const knobs = useMemo(
    () => [...(data?.knobs ?? [])].sort((a, b) => humanize(a.name).localeCompare(humanize(b.name))),
    [data]
  );
  const selected: FilterableKnob | undefined = knobs.find(knob => knob.name === knobName);
  const typeOperators = selected === undefined ? [] : operatorsFor(selected.knob_type);
  // The ordering operators never match a null, so asking about "not set" leaves
  // only equality. Offering them anyway lets the bar build `swap_round>=null`,
  // a condition no run can satisfy.
  const operators = value === NOT_SET_VALUE ? EQUALITY_OPERATORS : typeOperators;
  const effectiveOperator = operators.includes(operator) ? operator : (operators[0] ?? "");

  function selectKnob(name: string) {
    setKnobName(name);
    setOperator("");
    const next = knobs.find(knob => knob.name === name);
    // A boolean has a closed value set, so seed it rather than leaving the
    // control blank and the Add button disabled for no visible reason.
    setValue(next?.knob_type === "boolean" ? "true" : "");
  }

  function addFilter() {
    if (selected === undefined || effectiveOperator === "" || value === "") {
      return;
    }
    const encoded = `${selected.name}${effectiveOperator}${value}`;
    if (!filters.includes(encoded)) {
      onChange([...filters, encoded]);
    }
    setKnobName("");
    setOperator("");
    setValue("");
  }

  if (knobs.length === 0) {
    return null;
  }

  const canAdd = selected !== undefined && effectiveOperator !== "" && value !== "";

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <SlidersHorizontal className="h-3.5 w-3.5 text-muted-foreground" />

      <select
        aria-label="Knob to filter on"
        value={knobName}
        onChange={e => selectKnob(e.target.value)}
        className={cn(SELECT_CLASS, "max-w-56")}
      >
        <option value="">Filter by knob…</option>
        {knobs.map(knob => (
          <option key={knob.name} value={knob.name}>
            {humanize(knob.name)}
          </option>
        ))}
      </select>

      {selected !== undefined ? (
        <>
          <select
            aria-label="Comparison"
            value={effectiveOperator}
            onChange={e => setOperator(e.target.value)}
            className={cn(SELECT_CLASS, "font-mono")}
          >
            {operators.map(op => (
              <option key={op} value={op}>
                {op}
              </option>
            ))}
          </select>

          {selected.nullable ? (
            <label className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
              <input
                type="checkbox"
                checked={value === NOT_SET_VALUE}
                onChange={e => setValue(e.target.checked ? NOT_SET_VALUE : "")}
                className="h-3 w-3 rounded border-border accent-foreground"
              />
              not set
            </label>
          ) : null}

          {/* "not set" is the whole condition, so it replaces the value control. */}
          {value === NOT_SET_VALUE ? null : (
            <>
              {selected.knob_type === "boolean" ? (
                <select
                  aria-label="Value"
                  value={value}
                  onChange={e => setValue(e.target.value)}
                  className={SELECT_CLASS}
                >
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              ) : null}

              {selected.knob_type === "enum" ? (
                <select
                  aria-label="Value"
                  value={value}
                  onChange={e => setValue(e.target.value)}
                  className={SELECT_CLASS}
                >
                  <option value="">Choose…</option>
                  {(selected.enum_values ?? []).map(enumValue => (
                    <option key={enumValue} value={enumValue}>
                      {enumValue}
                    </option>
                  ))}
                </select>
              ) : null}

              {selected.knob_type !== "boolean" && selected.knob_type !== "enum" ? (
                <input
                  aria-label="Value"
                  type={selected.knob_type === "string" ? "text" : "number"}
                  value={value}
                  placeholder="value"
                  onChange={e => setValue(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === "Enter") {
                      addFilter();
                    }
                  }}
                  className={cn(SELECT_CLASS, "w-28 placeholder:text-muted-foreground")}
                />
              ) : null}
            </>
          )}

          <button
            type="button"
            disabled={!canAdd}
            onClick={addFilter}
            className="inline-flex items-center gap-0.5 rounded-md border border-border bg-muted/50 px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground transition-colors hover:border-primary hover:bg-primary/5 hover:text-foreground disabled:opacity-40 disabled:hover:border-border disabled:hover:bg-muted/50 disabled:hover:text-muted-foreground"
          >
            <Plus className="h-3 w-3" />
            Add
          </button>
        </>
      ) : null}

      {filters.map(raw => (
        <FilterChip
          key={raw}
          raw={raw}
          onRemove={() => onChange(filters.filter(entry => entry !== raw))}
        />
      ))}

      {filters.length > 0 ? (
        <button
          type="button"
          onClick={() => onChange([])}
          className="ml-1 inline-flex items-center gap-0.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
        >
          <XCircle className="h-3 w-3" />
          Clear
        </button>
      ) : null}
    </div>
  );
}
