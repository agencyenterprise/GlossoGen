# Changelog

Notable changes per release. Versions follow the `vX.Y.Z` tags on `main`.

## Unreleased

## v0.1.3

### Added
- A cost model in the README: which knobs drive spend, and the advice to price
  one run before launching a sweep.
- `SECURITY.md`, `CONTRIBUTING.md`, Dependabot, and issue and pull-request
  templates.
- Releases are cut from a pull-request label. `release:patch` / `release:minor` /
  `release:major` bump the version, tag it, and publish the images; `norelease`
  merges without shipping. New pull requests default to `release:patch`, and a
  required check enforces that exactly one label is set.
- `docker-compose.yml` and a self-hosting section in the README.

### Changed
- Deployment and the experimental record moved to separate repositories. The
  server image no longer carries a plotting stack or a multi-gigabyte ML stack
  to serve JSON; `torch` and friends are behind the `metrics-ml` extra and
  `inspect-ai` behind `evals`.
- Evaluation fails loudly. A metric that cannot run raises instead of returning
  an empty result, and the runner writes its report before re-raising so the
  exit status reflects the failure. Metrics that genuinely do not apply to a run
  still return nothing, as before.

### Fixed
- Prompt templates, knob defaults, probe question banks, and judge golden labels
  now ship inside the wheel. Only `.py` files were packaged, so installing
  `glossogen` as a dependency produced a package that could not render a prompt.
- Concurrent launches no longer truncate each other's logs. Launch output goes
  to one file per launch under `runs/_launch_logs/` instead of a single shared
  path opened in write mode.
- `project.version` now tracks the release tag. It read `0.1.0` for the `v0.1.1`
  release, so `importlib.metadata.version("glossogen")` reported the wrong
  version. `v0.1.1` itself cannot be corrected without moving a published tag.
- Scenarios that ship no frontend plug-in render their timeline against the
  right primary channel instead of an empty one.
- Image publishing triggers only on `vMAJOR.MINOR.PATCH`. The previous `v*`
  pattern also matched scenario tags such as `veyru-stellar-v1`.

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
