"use client";

import type { ReactNode } from "react";

export function LabelledRow({
  label,
  description,
  htmlFor,
  error,
  children,
}: {
  label: string;
  description: string | null;
  htmlFor: string | null;
  error: string | null;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1">
      {htmlFor ? (
        <label htmlFor={htmlFor} className="block text-sm font-medium">
          {label}
        </label>
      ) : (
        <span className="block text-sm font-medium">{label}</span>
      )}
      {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
      {children}
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
    </div>
  );
}
