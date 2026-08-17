# Changelog

Notable changes per release. Versions follow the `vX.Y.Z` tags on `main`.

## Unreleased

### Added
- `glossogen new-scenario <name> --target-dir <dir>` writes a scenario package of
  your own that already runs: `check-scenario` passes, `pytest` passes, and
  `glossogen run` completes before anything is edited. Assembling one by hand
  from the guide had two steps that fail long after the mistake, and both are now
  written for you: `package-data`, without which the wheel carries no prompt or
  preset and only an editable install works, and the entry-point key, which has
  to equal what `name()` returns or runs land where nothing looks for them. The
  generated package pins the glossogen release it was generated against, and
  carries tests written against `glossogen.testing`.
- Scenarios and metrics can ship in their own distributions. A package declares a
  scenario under the `glossogen.scenarios.v1` entry-point group and a metric under
  `glossogen.metrics`, and both are discovered, listed, runnable and scorable with
  no change to this repo. Presets and prompts are read from the contributing
  package. See [docs/creating-a-scenario.md](docs/creating-a-scenario.md) and
  [docs/creating-a-metric.md](docs/creating-a-metric.md).
- `docs/creating-a-metric.md`, covering the `Metric` contract, the empty-list
  convention, both registration paths, and how to run one.
- `glossogen check-scenario <name>` builds a scenario from every preset it ships
  and checks the contract the ABC cannot enforce: agents claiming channels
  nobody created, `tool_names` no tool answers to, `get_agent_roles` disagreeing
  with the agents that get built, templates that do not render, a config that
  does not round-trip through its own dump. The checks moved out of the test
  suite and into the package, because a scenario can ship from any distribution
  and the tests do not; the repository's conformance suite now runs the same
  ones over the built-ins. Reports every failure rather than the first, exits
  non-zero, and needs no API key.
- `glossogen.testing`, behind a `testing` extra: the harness that runs a scenario
  with the LLM replaced by a script. `check-scenario` proves a scenario builds,
  but never starts the game clock, so nothing there notices if the world's state
  machine, the postmortem phase or the round verdict breaks. `run_rounds` drives
  the real loop, and the `assert_*` helpers state what a finished run must
  contain. `metric_harness` scores a finished run the way `evaluate` does, and
  `assert_scenario_is_registered` catches the case `check-scenario` cannot, a
  name that resolves to somebody else's class. All of this was reachable only
  from this repository's own `tests/` directory, so a scenario in another package
  had no way to test itself without racing the clock.
  See [docs/testing-a-scenario.md](docs/testing-a-scenario.md).
- `glossogen serve --ui-port PORT` starts the web UI alongside the API, from the
  published frontend image, so someone whose scenario or metric lives in their own
  package reaches it without cloning this repository. The flag wires `API_URL`,
  adds the UI's origin to `ALLOWED_ORIGINS`, waits until the page answers, and
  removes the container when the server stops. `--ui-image` pins a version tag,
  which an older server needs.
- A `glossogen` console script, so the commands the docs spell as `glossogen ...`
  work on an installed package rather than only as `python -m glossogen`.
- Task-shaped documentation pages under `docs/`: installation, running
  simulations, evaluation, scenarios, agent swaps and resume, the web UI, MCP
  integration, and deployment.

### Fixed
- A run whose environment cannot reach a model it would call is refused at the
  command line, instead of starting and failing once the game clock has run its
  course. Agent runner tasks are awaited only after the clock finishes, so a
  missing credential used to surface after `round_count` rounds of
  `max_round_duration_seconds`, from a claimed run directory holding every
  agent's registration and no model call, with a zero exit status. The check
  covers the agents' providers, a `self-hosted` model that
  `SELF_HOSTED_BASE_URLS` does not serve, and the model a scenario judges its
  own rounds with, whose provider its knobs name independently of the run's.
  `replace-agent`, `cross-run-replace-agent`, `resume-at-round` and the MCP
  `start_run` tool check before claiming a directory too. A scheduled
  `swap_agent` is checked with the rest: it names its own model and is built at
  a round boundary, so an unreachable one used to cost every round before the
  swap, at full price, and then kill the agent it was meant to bring in. Only
  the boundaries a run will actually cross are checked, so resuming past a swap
  does not ask for the credential that swap needed: a resumed run inherits its
  source's whole schedule, and the clock never visits what is below where it
  opens.
- `hospital_bed_assignment_privacy` no longer declares `judge_model` /
  `judge_provider`. It scores its rounds by comparing what was transferred
  against the ground truth and reads neither knob; they were kept "for parity
  with other scenarios", which is how a scenario with no LLM anywhere came to
  refuse a run for want of an Anthropic key.
- `SimulationScenario.get_judge_models(knobs)` is where a scenario states the
  models it calls itself, and its answer is what the launch check believes. The
  default reports the `judge_model` / `judge_provider` pair; a scenario whose
  judge is conditional, or which names those knobs differently, overrides it and
  is not second-guessed, so a configuration that calls no judge is never asked
  for a credential it will not spend.

### Changed
- The published images are manifest lists covering `linux/amd64` and
  `linux/arm64`, each architecture built on a runner of its own and merged
  afterwards. An amd64-only image made every `docker run` on an Apple Silicon
  machine an explicit `--platform` and an emulated one. `serve --ui-port` still
  runs a release published before this, by retrying under emulation when the
  registry has no image for the host.
- The README is a short hub that links the pages above. It had grown to cover
  every subject at full depth, which meant the answer to "what is this and how do
  I run it" was buried. Its project-structure listing is gone rather than moved:
  it drifted from the tree every time a module was added.
- The metric catalogue in `docs/evaluation.md` covers every registered metric. The
  README's list was missing seven of them, including all of the deterministic
  language metrics.
- `Architecture.md`'s run-directory listing includes the per-metric sidecar files
  and the live-run `stream.json`.
- `scenario_loader.py` is the only way anything resolves a scenario name; nothing
  reads `SCENARIO_REGISTRY` directly any more.
- Knobs presets are served by `SimulationScenario.knobs_preset_names` /
  `load_knobs_preset` instead of by globbing a path under `glossogen/scenarios`,
  which removed a duplicated helper from the REST and MCP layers.
- `SimulationScenario.name()` is a classmethod, derived from the same package
  directory `scenario_package_files()` resolves.

### Fixed
- `--config` on `run`, and `--knobs` on the swap and resume flows, take the name
  of a preset the scenario ships. Both only accepted a file path, and presets
  live inside the scenario's own package: a checkout could write
  `src/glossogen/scenarios/veyru/knobs_default.json`, while an installed package
  left no sane thing to type at all. A path still wins when the argument is one,
  and an argument that is neither is refused by naming the presets that exist.
  `--config` is now required rather than silently accepting an empty
  configuration that every scenario's knobs model rejected a moment later.
- A `.env` in the working directory is read by an installed package, not only by
  a checkout. `python-dotenv` locates the file relative to the module that calls
  it, which lands in `site-packages` once glossogen is a dependency, so a
  project's own `.env` was ignored and its `ANTHROPIC_API_KEY` with it. Nothing
  reported this: the key was simply absent and the run failed later against the
  provider.

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
