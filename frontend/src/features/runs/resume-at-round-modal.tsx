"use client";

import { Loader2 } from "lucide-react";
import { useState } from "react";

interface ConfirmArgs {
  roundsAfterResume: number;
  knobs: Record<string, unknown> | null;
}

interface Props {
  isPending: boolean;
  isSuccess: boolean;
  errorMessage: string | null;
  roundStart: number;
  sourceRoundCount: number | null;
  onConfirm: (args: ConfirmArgs) => void;
  onCancel: () => void;
}

export function ResumeAtRoundModal({
  isPending,
  isSuccess,
  errorMessage,
  roundStart,
  sourceRoundCount,
  onConfirm,
  onCancel,
}: Props) {
  const defaultRoundsAfterResume =
    sourceRoundCount !== null ? Math.max(1, sourceRoundCount - roundStart) : 1;
  const [roundsAfterResume, setRoundsAfterResume] = useState<number>(defaultRoundsAfterResume);
  const [knobsText, setKnobsText] = useState<string>("");
  const [knobsError, setKnobsError] = useState<string | null>(null);

  function handleConfirmClick() {
    const trimmed = knobsText.trim();
    let knobs: Record<string, unknown> | null = null;
    if (trimmed !== "") {
      try {
        const parsed: unknown = JSON.parse(trimmed);
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          setKnobsError("Knob overrides must be a JSON object");
          return;
        }
        knobs = parsed as Record<string, unknown>;
      } catch (exc) {
        setKnobsError(exc instanceof Error ? exc.message : "Invalid JSON");
        return;
      }
    }
    setKnobsError(null);
    onConfirm({ roundsAfterResume, knobs });
  }

  const canSubmit = !isPending && !isSuccess && roundsAfterResume >= 1;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/40 px-4 py-4">
      <div className="flex min-h-full items-center justify-center">
        <div className="flex w-full max-w-md max-h-[calc(100vh-2rem)] flex-col overflow-hidden rounded-xl border border-border bg-background shadow-xl">
          <div className="min-h-0 flex-1 overflow-y-auto p-5">
            <h3 className="mb-3 text-sm font-medium">Resume at start of round {roundStart}</h3>
            <p className="mb-3 text-xs text-muted-foreground">
              Clones the source run at the round {roundStart} commit and resumes execution. Every
              agent keeps its full reconstructed history; no agent is restarted. Optional knob
              overrides are shallow-merged onto the source&apos;s scenario config — useful for
              flipping <code className="rounded bg-muted px-1">postmortem_enabled</code>, scheduling
              post-hoc swaps via <code className="rounded bg-muted px-1">scheduled_events</code>, or
              extending <code className="rounded bg-muted px-1">round_count</code>.
            </p>

            <div className="mb-4 space-y-1">
              <label className="block text-sm font-medium" htmlFor="rounds-after-resume">
                Rounds after resume
              </label>
              <p className="text-[11px] text-muted-foreground">
                The resumed simulation plays this many rounds following round {roundStart}.
                {sourceRoundCount !== null ? ` Source ran ${sourceRoundCount} rounds total.` : ""}
              </p>
              <input
                id="rounds-after-resume"
                type="number"
                min={1}
                className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
                value={roundsAfterResume}
                onChange={e => setRoundsAfterResume(Math.max(1, Number(e.target.value) || 1))}
                disabled={isPending}
              />
            </div>

            <div className="mb-4 space-y-1">
              <label className="block text-sm font-medium" htmlFor="knobs-overrides">
                Knob overrides (JSON, optional)
              </label>
              <p className="text-[11px] text-muted-foreground">
                Shallow-merged onto the source&apos;s scenario_config. Leave blank to inherit the
                source unchanged.
              </p>
              <textarea
                id="knobs-overrides"
                rows={6}
                spellCheck={false}
                placeholder={'{\n  "postmortem_enabled": true\n}'}
                className="w-full rounded-md border border-border bg-background px-2 py-1 font-mono text-[12px]"
                value={knobsText}
                onChange={e => {
                  setKnobsText(e.target.value);
                  if (knobsError !== null) {
                    setKnobsError(null);
                  }
                }}
                disabled={isPending}
              />
              {knobsError !== null ? (
                <p className="text-[11px] text-destructive">{knobsError}</p>
              ) : null}
            </div>

            {isPending ? (
              <div className="mt-4 flex items-start gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-[11px] text-muted-foreground">
                <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin" />
                <div className="space-y-0.5">
                  <p className="font-medium text-foreground">Launching resume-at-round…</p>
                  <p>
                    Cloning the source, rewriting the JSONL, and starting the resumed simulation.
                    Usually 10–20 seconds. Redirecting when ready.
                  </p>
                </div>
              </div>
            ) : null}

            {isSuccess ? (
              <div className="mt-4 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-[11px] text-emerald-700 dark:text-emerald-300">
                Launched. Redirecting to the new run…
              </div>
            ) : null}

            {errorMessage !== null ? (
              <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-[11px] text-destructive">
                <p className="font-medium">Resume-at-round failed</p>
                <p className="mt-0.5 wrap-break-word">{errorMessage}</p>
              </div>
            ) : null}
          </div>

          <div className="flex shrink-0 justify-end gap-2 border-t border-border px-5 py-3">
            <button
              className="rounded-md border border-border px-3 py-1 text-[12px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              onClick={onCancel}
              disabled={isPending}
            >
              {errorMessage !== null ? "Close" : "Cancel"}
            </button>
            <button
              className="rounded-md bg-foreground px-3 py-1 text-[12px] font-medium text-background transition-opacity hover:opacity-80 disabled:opacity-50"
              onClick={handleConfirmClick}
              disabled={!canSubmit}
            >
              {isPending
                ? "Launching..."
                : isSuccess
                  ? "Redirecting…"
                  : errorMessage !== null
                    ? "Retry"
                    : "Launch resume"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
