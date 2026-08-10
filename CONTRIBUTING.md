# Contributing

Thanks for your interest. This is a research platform, so the bar is less about
polish and more about **not silently producing wrong numbers**. Most of the
conventions below exist for that reason.

## Getting set up

See [README](README.md#setup) for prerequisites and installation. In short:

```bash
make install          # backend + frontend
make install-metrics  # add this if you will run evaluations (pulls torch)
make lint             # must pass before you open a PR
```

`make lint` runs black, isort, ruff, pyright in **strict** mode, vulture, and two
custom linters, plus prettier/eslint/stylelint/tsc on the frontend. CI runs the
same thing, so a clean local run means a clean CI run.

## Before you open a PR

- [ ] `make lint` passes
- [ ] `make gen-api-types` produces no diff if you touched a response model — CI fails on drift
- [ ] Docstrings on new modules and public functions
- [ ] No dead code left behind

## Conventions worth knowing

These are enforced by linters or review, and they surprise people:

**Fail loudly, never silently.** If something cannot run, raise. A missing
dependency, an unreadable config, an impossible state — all should stop the
process with a message naming the cause and the fix. An empty result is
indistinguishable from a legitimately empty one, and in a research codebase that
means publishing numbers nobody computed.

The one exception is a metric that genuinely does not apply to a run — no primary
channel, no resume boundary. Those return no measurement and do not fail, because
nothing is broken.

**No default parameter values.** Callers pass everything explicitly. If that makes
a call site awkward, that is usually a sign the function is doing too much.

**Always use named arguments** when calling functions.

**Never return bare dicts.** Use a `NamedTuple` or a Pydantic model. Every FastAPI
endpoint declares a `response_model` and returns an instance of it.

**No inline imports** and **no `TYPE_CHECKING`** blocks — both are enforced by
custom linters in `linter/`. If you hit a circular import, restructure rather than
working around it. Conditional loading of an optional dependency goes through
`importlib.import_module`, as in
[optional_ml_backend.py](src/glossogen/evaluation/metric_core/optional_ml_backend.py).

**Prompts live in Jinja templates**, never hardcoded in Python. They ship inside
the package, so a new `prompts/` directory needs no packaging change — but a new
file *extension* does, via `[tool.setuptools.package-data]`.

**LLM output is parsed through a schema.** Define a Pydantic model, pass it to
`generate_structured()`, use the validated instance. Never parse free text.

**Docs describe the current state.** No "this now uses X instead of Y" — the
reader does not know what Y was and does not care.

## Adding a scenario

Open a pull request with the scenario rather than an issue proposing one. A
scenario is self-contained — its own package under
`src/glossogen/scenarios/<name>/`, touching no shared code.

[docs/creating-a-scenario.md](docs/creating-a-scenario.md) is the step-by-step
guide.

## Releases

Releases are cut by labelling a pull request with exactly one of `release:patch`,
`release:minor`, `release:major`, or `norelease`. New pull requests get
`release:patch` automatically — change it if the work is a new feature, a breaking
change, or should not ship yet. A required check enforces that exactly one is set,
so merging always means something explicit.

Merging a labelled pull request runs `uv version --bump <label>`, commits the new
version, tags it `vX.Y.Z`, and publishes the backend and frontend images to GHCR.

**Do not edit `project.version` in `pyproject.toml` yourself** — the release commit
sets it. Keeping the bump and the tag in one automated step is what stops the two
drifting, which is what happened while it was a manual step.

Tagging `vX.Y.Z` by hand still publishes images, for the cases the label flow does
not cover.

## Costs

Running simulations spends real money against your own provider keys. Before
launching anything larger than a smoke test, read
[the cost model](README.md#understanding-cost). A misconfigured sweep is an
expensive mistake and an easy one to make.

## Reporting bugs

Open an issue with the version or commit, what you expected, what happened, and
the relevant log lines. For anything security-related, follow
[SECURITY.md](SECURITY.md) instead — do not open a public issue.
