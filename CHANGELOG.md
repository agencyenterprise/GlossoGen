# Changelog

Notable changes per release. Versions follow the `vX.Y.Z` tags on `main`.

## Unreleased

### Added
- Concurrency ceilings on the paid background work the server spawns:
  `MAX_CONCURRENT_RUNS` and `MAX_CONCURRENT_EVALUATIONS` (default 4 each).
  Exceeding a limit returns HTTP 429. Previously both were unbounded, so a
  retry loop in a client could run up an unbounded provider bill.
- `SECURITY.md`, `CONTRIBUTING.md`, Dependabot, and issue and pull-request
  templates.

### Fixed
- Concurrent launches no longer truncate each other's logs. Launch output goes
  to one file per launch under `runs/_launch_logs/` instead of a single shared
  path opened in write mode.
- Temporary launch config files are swept after 24 hours instead of
  accumulating in the system temp directory for the life of the container.
- `project.version` now tracks the release tag. It read `0.1.0` for the `v0.1.1`
  release, so `importlib.metadata.version("glossogen")` reported the wrong
  version. `v0.1.1` itself cannot be corrected without moving a published tag.

## v0.1.1

### Fixed
- Built wheels shipped no runtime data files. Only `.py` files were packaged, so
  139 Jinja prompt templates, 27 JSON knob defaults and probe question banks, and
  the judge golden labels were missing. Installing `glossogen` as a dependency
  produced a package that could not render a prompt. Source checkouts and the
  Docker image were unaffected, which is why it went unnoticed.

### Removed
- `AuthGate`, a pass-through component that rendered its children unchanged.
- `aiosqlite` and `watchdog`, declared dependencies with no imports.

## v0.1.0

First tagged release.

### Changed
- Repository scoped to the platform. Experiment configurations and analysis
  tooling moved out, along with 35 of 37 entries in `scripts/`.
- `torch`, `transformers`, `minicons`, and `datasets` moved to an optional
  `metrics-ml` extra; `inspect-ai` to `evals`. Plotting and dataframe libraries
  dropped entirely. The backend image went from 5.82 GB to 480 MB.
- Frontend configuration is read at request time rather than compiled into the
  bundle, so one image serves any environment. `NEXT_PUBLIC_API_URL` and
  `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` became `API_URL` and
  `CLERK_PUBLISHABLE_KEY`, read at runtime.
- Evaluation fails loudly when a requested metric cannot run. Previously a
  crashing metric was logged and the process still exited zero, so a broken
  environment was indistinguishable from a clean run.
