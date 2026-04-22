"use client";

import { useId } from "react";
import { LabelledRow } from "./labelled-row";

export function Toggle({
  label,
  description,
  value,
  onChange,
  disabled,
}: {
  label: string;
  description: string | null;
  value: boolean;
  onChange: (next: boolean) => void;
  disabled: boolean;
}) {
  const inputId = useId();
  return (
    <LabelledRow label={label} description={description} htmlFor={inputId} error={null}>
      <label
        htmlFor={inputId}
        className={`inline-flex items-center gap-2 text-sm ${
          disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"
        }`}
      >
        <input
          id={inputId}
          type="checkbox"
          checked={value}
          disabled={disabled}
          onChange={e => onChange(e.target.checked)}
          className="h-4 w-4 rounded border-input accent-primary focus:outline-none focus:ring-1 focus:ring-primary"
        />
        <span className="text-muted-foreground">{value ? "On" : "Off"}</span>
      </label>
    </LabelledRow>
  );
}
