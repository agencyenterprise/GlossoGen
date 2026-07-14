/**
 * Generic renderers for scenario-specific timeline markers.
 *
 * A `ScenarioTimelineMarker` (produced by a scenario plug-in from the run's
 * `scenario_extras`) is drawn two ways: `ScenarioMarkerFab` as a floating
 * jump-to button stacked on the run-detail page, and `ScenarioMarkerDivider`
 * as an inline divider inside the chat pane at the marker's round. Both are
 * tone-driven, so no scenario names appear here.
 */

import type { ScenarioMarkerTone, ScenarioTimelineMarker } from "./scenario-plugin";
import { bottomClass } from "./fork-badge";

const FAB_TONE_CLASSES: Record<ScenarioMarkerTone, string> = {
  amber:
    "border-amber-300/60 bg-amber-50 text-amber-700 hover:bg-amber-100 dark:border-amber-700/50 dark:bg-amber-950/80 dark:text-amber-300 dark:hover:bg-amber-900/80",
  emerald:
    "border-emerald-300/60 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 dark:border-emerald-700/50 dark:bg-emerald-950/80 dark:text-emerald-300 dark:hover:bg-emerald-900/80",
  violet:
    "border-violet-300/60 bg-violet-50 text-violet-700 hover:bg-violet-100 dark:border-violet-700/50 dark:bg-violet-950/80 dark:text-violet-300 dark:hover:bg-violet-900/80",
};

const DIVIDER_TONE_CLASSES: Record<ScenarioMarkerTone, string> = {
  amber: "border-amber-400/80 bg-amber-50 dark:border-amber-600/70 dark:bg-amber-950/50",
  emerald: "border-emerald-400/80 bg-emerald-50 dark:border-emerald-600/70 dark:bg-emerald-950/50",
  violet: "border-violet-400/80 bg-violet-50 dark:border-violet-600/70 dark:bg-violet-950/50",
};

const DIVIDER_TITLE_TONE_CLASSES: Record<ScenarioMarkerTone, string> = {
  amber: "text-amber-800 dark:text-amber-200",
  emerald: "text-emerald-800 dark:text-emerald-200",
  violet: "text-violet-800 dark:text-violet-200",
};

const DIVIDER_SUBTITLE_TONE_CLASSES: Record<ScenarioMarkerTone, string> = {
  amber: "text-amber-700/80 dark:text-amber-300/80",
  emerald: "text-emerald-700/80 dark:text-emerald-300/80",
  violet: "text-violet-700/80 dark:text-violet-300/80",
};

interface ScenarioMarkerFabProps {
  marker: ScenarioTimelineMarker;
  stackIndex: number;
  onClick: () => void;
}

/** Floating action button that scrolls to a scenario marker's divider. */
export function ScenarioMarkerFab({ marker, stackIndex, onClick }: ScenarioMarkerFabProps) {
  const Icon = marker.icon;
  return (
    <button
      onClick={onClick}
      className={`fixed ${bottomClass(stackIndex)} right-6 z-40 flex items-center gap-1.5 rounded-full border px-3 py-2 text-xs font-medium shadow-lg transition-all hover:shadow-xl ${FAB_TONE_CLASSES[marker.tone]}`}
      title={`Go to ${marker.fabLabel} (round ${marker.roundNumber})`}
    >
      <Icon className="h-3.5 w-3.5" />
      Go to {marker.fabLabel} (round {marker.roundNumber})
    </button>
  );
}

interface ScenarioMarkerDividerProps {
  marker: ScenarioTimelineMarker;
}

/** Inline chat-pane divider marking a scenario event at the start of a round. */
export function ScenarioMarkerDivider({ marker }: ScenarioMarkerDividerProps) {
  const Icon = marker.icon;
  return (
    <div
      id={marker.id}
      className={`mx-4 my-4 rounded-md border-2 border-dashed px-4 py-3 ${DIVIDER_TONE_CLASSES[marker.tone]}`}
    >
      <div
        className={`flex items-center justify-center gap-2 ${DIVIDER_TITLE_TONE_CLASSES[marker.tone]}`}
      >
        <Icon className="h-4 w-4" />
        <span className="text-sm font-semibold">{marker.dividerTitle}</span>
      </div>
      <div className={`mt-1 text-center text-[11px] ${DIVIDER_SUBTITLE_TONE_CLASSES[marker.tone]}`}>
        {marker.dividerSubtitle}
      </div>
    </div>
  );
}
