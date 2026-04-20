"use client";

import { useId, useState } from "react";
import { LabelledRow } from "./labelled-row";

export function NumberInput({
  label,
  description,
  value,
  onChange,
  min,
  max,
  step,
  unit,
  error,
  nullable,
  disabled,
}: {
  label: string;
  description: string | null;
  value: number | null;
  onChange: (next: number | null) => void;
  min: number | null;
  max: number | null;
  step: number;
  unit: string | null;
  error: string | null;
  nullable: boolean;
  disabled: boolean;
}) {
  const inputId = useId();
  const [text, setText] = useState<string>(value === null ? "" : String(value));
  const [lastSyncedValue, setLastSyncedValue] = useState<number | null>(value);
  if (lastSyncedValue !== value) {
    setLastSyncedValue(value);
    setText(value === null ? "" : String(value));
  }

  function handleChange(raw: string) {
    setText(raw);
    if (raw === "") {
      if (nullable) {
        onChange(null);
      }
      return;
    }
    const parsed = Number(raw);
    if (Number.isFinite(parsed)) {
      onChange(parsed);
    }
  }

  return (
    <LabelledRow label={label} description={description} htmlFor={inputId} error={error}>
      <div className="flex items-center gap-2">
        <input
          id={inputId}
          type="number"
          value={text}
          onChange={e => handleChange(e.target.value)}
          min={min === null ? undefined : min}
          max={max === null ? undefined : max}
          step={step}
          disabled={disabled}
          className={`w-32 rounded-md border bg-background px-3 py-1.5 text-sm outline-none focus:border-primary disabled:bg-muted disabled:text-muted-foreground ${
            error ? "border-destructive" : "border-input"
          }`}
        />
        {unit ? <span className="text-xs text-muted-foreground">{unit}</span> : null}
      </div>
    </LabelledRow>
  );
}
