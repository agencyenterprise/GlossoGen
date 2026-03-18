import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";

type Verdict = components["schemas"]["Verdict"];

const VERDICT_STYLES: Record<Verdict, { light: string; dark: string }> = {
  pass: { light: "bg-green-100 text-green-800", dark: "dark:bg-green-900/30 dark:text-green-400" },
  fail: { light: "bg-red-100 text-red-800", dark: "dark:bg-red-900/30 dark:text-red-400" },
  partial: {
    light: "bg-amber-100 text-amber-800",
    dark: "dark:bg-amber-900/30 dark:text-amber-400",
  },
};

const FALLBACK = "bg-muted text-muted-foreground";

export function VerdictPill({ verdict }: { verdict: Verdict | string }) {
  const style = VERDICT_STYLES[verdict as Verdict];
  return (
    <span
      className={cn(
        "inline-block min-w-[46px] rounded-full px-1.5 py-0.5 text-center text-[11px] font-medium leading-none",
        style ? `${style.light} ${style.dark}` : FALLBACK
      )}
    >
      {verdict}
    </span>
  );
}
