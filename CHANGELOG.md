# Changelog

Notable changes per release. Versions follow the `vX.Y.Z` tags on `main`.

Releases `v0.1.4` through `v0.2.7` are not itemized here: the file went unwritten
while they were cut. Their contents are in
[the releases page](https://github.com/agencyenterprise/GlossoGen/releases) and in
the commit log.

## Unreleased

### Added
- In-product analysis: pick a cohort of runs, group and filter it, chart metrics from
  the evaluation reports, and save the result as a dashboard the rest of the group can
  open. The same queries run from `glossogen analyze` with no server and no database,
  so a chart's numbers are checkable from a terminal. Dashboards live in Postgres when
  `DATABASE_URL` is set and in the runs directory when it is not.
  See [docs/analysis.md](docs/analysis.md).

## v0.5.0

### Added
- Exporting many runs at once, as raw run folders or as CSV tables, over REST and from
  `glossogen export`. See [docs/exporting-runs.md](docs/exporting-runs.md).

## v0.4.0

### Changed
- **Authentication is a plug-in, and this repository ships none.** Multi-tenancy stays:
  the `groups` table, `/api/g/{group_slug}/` routing, and the `Identity` attached to
  every request. What left is any knowledge of how a caller proves who they are. A
  deployment supplies that as a distribution declaring one entry point under
  `glossogen.identity_provider.v1`, implementing
  [`IdentityProvider`](src/glossogen/server/identity/identity_provider.py).

  With no provider installed the server is single-tenant: every request resolves to the
  synthetic `local` group. That is why there is no built-in implementation of the
  contract and why nothing in it is optional, and it is also why the server performs no
  authentication in that mode and should not be exposed to a network.

  The middleware keeps the parts a provider must not get wrong. It extracts the bearer
  credential, parses the URL's group slug, and resolves that slug to a `groups` row
  *before* calling `resolve_identity`, so a provider never queries that table and cannot
  get tenancy isolation wrong. It answers one question: does this credential grant
  access to this group, and as whom. The other direction of the seam is
  [`provider_services.py`](src/glossogen/server/identity/provider_services.py), which
  exists because that direction was previously undeclared: the one call a provider must
  make to finish a deferred MCP authorization was reachable only by reaching into
  `request.app.state`.

  Ambiguity refuses to boot. Two declared providers, or one declared under a contract
  version this platform does not read, raises. The scenario and metric loaders warn and
  carry on in the same situation, which is right for them, because a missing scenario is
  a missing feature. A missing auth provider is a server that authenticates nothing
  while an operator believes it is protected, and that is indistinguishable from a
  deployment that never configured one.

  Deferred OAuth consent stays platform code: parking a request is about having more
  than one group to choose from, not about any one vendor, and `approve_pending_consent`
  already took a resolved `group_id`. Only the approval endpoint is pluggable.
  `GET /mcp/whoami` stays too, since `glossogen whoami` calls it in either mode.
- The frontend reads identity through an adapter contract,
  `frontend/src/features/auth/auth-adapter.ts`, implemented under
  `frontend/src/features/auth/adapter/`. The copy here answers "no provider configured"
  to every slot. Four modules rather than one object, because React's module graph
  forbids one: `readSession` needs a server-only import, the provider wrapper is a
  client component, `getSessionToken` runs in the browser with no React so
  `api-client.ts` stays importable from either side, and the proxy delegate runs in the
  edge runtime. `/sign-in`, `/sign-up`, `/select-org` and `/mcp-consent` stay here as
  shells, because the App Router resolves pages by file path.
- `CLERK_PUBLISHABLE_KEY` became `AUTH_PUBLIC_PUBLISHABLE_KEY`, and `RuntimeConfig`
  gained an `auth` map collected from every `AUTH_PUBLIC_*` variable rather than a named
  field, since the platform cannot know what values a provider needs. The request-time
  read is unchanged, so one compiled image still serves any environment. Those values
  reach the browser and are visible in page source; an adapter's secrets stay on the
  server.

### Removed
- `clerk-backend-api` and `svix` dependencies, and every Clerk-specific module. A
  deployment that used Clerk installs a provider distribution supplying it.
- `CLERK_*` variables from `.env.example`, `docker-compose.yml` and the documentation.
  A provider reads whatever it needs from the environment; the platform reads none of
  them.

### Migration
- `groups.clerk_org_id` is renamed `external_org_id` by migration
  `0005_rename_external_org_id`, along with its index and the auto-generated `UNIQUE`
  constraint, which `ALTER TABLE ... RENAME COLUMN` leaves behind. The column holds the
  id a group carries in whichever provider a deployment configures, so naming it after
  one made the schema describe a deployment choice.
- A deployment currently relying on `CLERK_SECRET_KEY` must install an identity
  provider before upgrading. Without one the server starts in single-tenant mode and
  authenticates nobody, which is a silent change in posture rather than an error.

## v0.3.0

### Added
- `validate` now checks a scenario's events and the hooks its metrics read. Events
  were covered by nothing at all, and each failure there is
  silent when it happens: an `event_type` repeating one the platform or another of
  the scenario's own answers to shadows one side of the parser, so the run writes
  fine and reads back afterwards as the other thing; an `events` module that raises
  is logged and skipped by discovery, deliberately, so a third-party plug-in cannot
  stop the platform reading unrelated logs, which also means its author is never
  told; and an `events.py` importing `glossogen.models.event` closes the cycle that
  module builds its union inside, which is read from the source rather than by
  importing, since by then the platform has failed to start. On the metric side, a
  probe or explanation config naming a file that is not there makes every metric in
  that family report having nothing to measure, which is what a run with nothing to
  measure reports too. `get_judge_models` is checked for readability and never
  compared against the knobs: that comparison was written and removed while the
  launch check was being added, because a scenario scoring its rounds without an LLM
  declared the knobs anyway and comparing the two refused runs for a credential it
  would never spend. What the hook reports is the scenario's to decide.
- A documentation site, built with mkdocs-material and published per release with
  `mike`, so a reader who pinned a tag gets the contract that tag was written
  against rather than whatever main says. `make docs-serve` previews it and `make
  docs-build` runs `mkdocs build --strict`, which a CI job runs on every PR.
  The obstacle was that these files are written to be read in the repository:
  dozens of links point into `src/`, into `tests/`, or at a root file, and every one
  of them resolves on GitHub and 404s on a site. `scripts/docs_hooks.py` rewrites
  those to permalinks at build time and adds the repository-root pages to the site
  from where they are, so nothing had to move and no link had to become an absolute
  URL in the markdown. Heading anchors now follow GitHub's slug rules for the same
  reason: a heading holding `&` or an arrow used to get one anchor in the repository
  and a different one on the site, so a link written against either was broken on
  the other.
- Three runnable notebooks under [notebooks/](notebooks/), executed in CI. They
  generate their own simulation through `glossogen.testing` rather than reading a
  committed run or asking for one first, so they need no API key and reach no
  network: the real MCP server, game clock, world and event logger, with only the
  model scripted. A committed run would go stale against the event schema, and a
  reader without credentials would be stuck at the first cell. `make
  install-notebooks` adds jupyter, pandas and matplotlib as a `notebooks`
  dependency group, kept out of `dev` so the default install and the test suite
  carry none of it. `make test-notebooks` executes every cell and fails on the
  first that raises, and `linter/check_notebook_outputs.py` in `make lint` refuses a
  notebook committed with its output, which otherwise buries the next real diff under
  regenerated cells.
- [docs/quickstart.md](docs/quickstart.md), a sequenced path through the platform:
  run a simulation, read its event log, score it with the metrics that spend
  nothing, then generate a scenario of your own and validate it. The reference
  documentation covered all of this and sequenced none of it, so the shortest route
  in was a 720-line guide read top to bottom. Costs are measured from three real
  runs rather than estimated: `warehouse_robot_recovery` is $0.16 to $0.34 at three
  rounds on haiku, `container_yard_stacking` $37 to $50 at fifteen on opus, and three
  identical haiku runs scored 0/3, 1/3 and 0/3.
- `linter/check_prompt_templates.py`, in `make lint`, checks the Jinja prompt
  templates: that each one parses under the environment that renders it, that
  every `{% include %}` names a partial in the directory the renderer searches,
  that nothing is rendered or included in vain, and that every template name in
  shipped code answers to a file. Nothing read the templates until a run did, and
  each of those failures otherwise waits until the run directory has been claimed and
  the agents have connected. Undeclared variables
  are deliberately left to `StrictUndefined` at render: scenarios assemble their
  template variables in helpers, so the set a template renders with cannot be
  decided from the call site, and a rule that guessed would report the templates
  that are fine. Prompt-sized string literals in scenario Python are advisory.
- `glossogen validate <name-or-directory>` replaces `check-scenario`, and takes
  either. Given a directory it reads the scenario's declaration out of that tree's
  own `pyproject.toml`, so an author's loop is edit then check rather than edit,
  reinstall, check: every other way into a scenario resolves a name through
  installed metadata. Given a name it resolves the installed scenario. The two forms
  cannot be
  confused, a scenario name being a bare lowercase identifier, so anything holding
  a dot or a separator is a path. A directory additionally gets four checks that
  stop meaning anything after installation, because installation is what hides
  them: `package-data` not covering the prompts and presets, which
  leaves an editable install working and the wheel rendering nothing; an
  entry-point group naming a contract version this platform does not read, which
  makes a scenario absent rather than refused; a non-empty package `__init__`,
  which closes the cycle event discovery runs inside; and a name something else
  already answers to, which is the one thing the name form cannot report, since it
  resolves to the scenario holding the name and reports that one as healthy.
  Needs no API key, and checks no model's reachability: describing a scenario must
  not require a credential.
- `glossogen new-scenario <name> --target-dir <dir>` writes a scenario package of
  your own that already runs: `validate` passes, `pytest` passes, and
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
- `glossogen validate <name>` builds a scenario from every preset it ships
  and checks the contract the ABC cannot enforce: agents claiming channels
  nobody created, `tool_names` no tool answers to, `get_agent_roles` disagreeing
  with the agents that get built, templates that do not render, a config that
  does not round-trip through its own dump. The checks moved out of the test
  suite and into the package, because a scenario can ship from any distribution
  and the tests do not; the repository's conformance suite now runs the same
  ones over the built-ins. Reports every failure rather than the first, exits
  non-zero, and needs no API key.
- `glossogen.testing`, behind a `testing` extra: the harness that runs a scenario
  with the LLM replaced by a script. `validate` proves a scenario builds,
  but never starts the game clock, so nothing there notices if the world's state
  machine, the postmortem phase or the round verdict breaks. `run_rounds` drives
  the real loop, and the `assert_*` helpers state what a finished run must
  contain. `metric_harness` scores a finished run the way `evaluate` does, and
  `assert_scenario_is_registered` catches the case validating by name cannot, a
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
- **`glossogen check-scenario` is now `glossogen validate`**, which takes a
  scenario name exactly as `check-scenario` did, and also takes a directory. Two
  commands differing only in how they found the class read as two different checks,
  and the second one existed to avoid renaming the first. Update any CI step that
  calls `check-scenario <name>` to `validate <name>`; nothing else about it changed.
- `validate` renders every round's injection rather than only round one. Round one is not representative: scenarios swap templates per round
  and bring an agent in partway through, so a template first reached at round 12
  used to cost the eleven rounds before it to discover. The failure names the round
  and the agent. What this still cannot reach is the branch reading a previous
  round's outcome, since nothing has been played; that belongs to the round loop,
  and `run_rounds(round_count=2)` covers it.
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
