/**
 * Whether a selection has been narrowed at all.
 *
 * An empty filter selection means every run the group owns, and answering it reads one
 * evaluation report per run: thousands of files, for a chart nobody has asked for yet.
 * So a selection that names nothing is not queried, and the surface says what to pick
 * instead.
 *
 * It is a deliberate floor, not a limit: naming one scenario or one label is enough,
 * and a cohort of every veyru run is still a cohort.
 */

import type { RunSelection } from "./use-analysis-data";

export function isNarrowedSelection(selection: RunSelection): boolean {
  if (selection.kind === "explicit") {
    return selection.run_ids.length > 0;
  }
  return (
    selection.scenario.length > 0 ||
    selection.labels.length > 0 ||
    selection.run_id_contains !== null ||
    selection.status !== null ||
    selection.contains_agent_id !== null
  );
}
