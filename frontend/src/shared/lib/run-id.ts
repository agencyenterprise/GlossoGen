export type RunIdParts = {
  scenario: string;
  run_dir_name: string;
};

export function splitRunId(runId: string): RunIdParts {
  const slashIndex = runId.indexOf("/");
  if (slashIndex === -1) {
    throw new Error(`Invalid run id (missing scenario prefix): ${runId}`);
  }
  return {
    scenario: runId.slice(0, slashIndex),
    run_dir_name: runId.slice(slashIndex + 1),
  };
}
