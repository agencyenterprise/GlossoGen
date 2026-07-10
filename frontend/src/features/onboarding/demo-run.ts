import type { components } from "@/types/api.gen";

/**
 * Loader for the frozen demo run served as a static asset on the public
 * landing-page walkthrough. The JSON is produced offline by
 * ``scripts/generate_demo_snapshot.py`` and has the exact shape of the
 * authenticated run-detail endpoint's ``RunDetailResponse``.
 */

type RunDetailResponse = components["schemas"]["RunDetailResponse"];

/** Static-asset URL of the serialized demo run (see public/demo/run.json). */
export const DEMO_RUN_URL = "/demo/run.json";

export async function loadDemoRun(): Promise<RunDetailResponse> {
  // eslint-disable-next-line no-restricted-globals -- static same-origin asset, not an API call
  const response = await fetch(DEMO_RUN_URL);
  if (!response.ok) {
    throw new Error(`Failed to load demo run: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as RunDetailResponse;
}
