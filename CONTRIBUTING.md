# Contributing

Thanks for your interest. This is a research platform, so the bar is less about
polish and more about **not silently producing wrong numbers**. Most of the
conventions below exist for that reason.

## Getting set up

See [Installation](docs/installation.md) for prerequisites and the full setup. In
short:

```bash
make install          # backend + frontend
make install-metrics  # add this if you will run evaluations (pulls torch)
make lint             # must pass before you open a PR
```

`make lint` runs black, isort, ruff, pyright in **strict** mode, vulture, and the
custom linters in `linter/`, plus prettier/eslint/stylelint/tsc on the frontend. CI
runs the same thing, so a clean local run means a clean CI run.

## Before you open a PR

- [ ] `make lint` passes
- [ ] `make test` passes
- [ ] `make gen-api-types` produces no diff if you touched a response model (CI fails on drift)
- [ ] Docstrings on new modules and public functions
- [ ] No dead code left behind

## Tests

`make test` runs the suite, in parallel across your cores. It needs no API keys
and reaches no network: agents run on a scripted fake model, so the result is the
same on your machine as in CI.

```
tests/fakes/       a pydantic-ai model that plays a written script, and a stub LLM provider
tests/unit/        one module at a time
tests/engine/      the declarative round engine, against recorded baselines
tests/scenarios/   one scenario at a time, driven through its own tools
tests/metrics/     one metric at a time, sharing one simulated run
tests/integration/ a real simulation, with only the model faked
tests/conformance/ every registered scenario against the platform's contract
```

The harness those tests run on is not in `tests/`. It lives in
`src/glossogen/testing/` and ships in the package behind the `testing` extra, so a
scenario in another distribution tests itself the same way the built-ins do. See
[Testing a scenario](docs/testing-a-scenario.md).

The conformance suite is parametrized over the scenario registry and every knobs
preset in the tree, so a new scenario is covered the moment it is registered.
Adding a rule there applies it to every existing scenario at once, which is the
cheapest place to catch the mistakes that only show up minutes into a run.

A few tests need the optional `metrics-ml` extra, which downloads and runs a
real model. They are skipped by default and named in the skip reason:

```bash
uv sync --extra metrics-ml
VIRTUAL_ENV= uv run --no-sync python -m pytest tests/ --metrics-ml
```

Everything else about those metrics is covered without the extra. The
`english_ngram_*` pair loads a hand-built model from its cache, and `perplexity`
runs its aggregation against an injected scorer, so only the real forward pass
is behind the flag.

For coverage, `make test-cov` writes `.coverage` and prints the uncovered lines;
`make coverage-html` renders it browsable at `htmlcov/index.html`. CI runs
`make test-cov` on every PR and posts a comment with the total, the change
against `main`, and how much of your diff is covered. Whole subsystems are still
uncovered, so the total moving down is not automatically a problem. What the
comment is really for is the diff column: code you added that nothing runs.

## Conventions worth knowing

These are enforced by linters or review, and they surprise people:

**Fail loudly, never silently.** If something cannot run, raise. A missing
dependency, an unreadable config, an impossible state: all should stop the
process with a message naming the cause and the fix. An empty result is
indistinguishable from a legitimately empty one, and in a research codebase that
means publishing numbers nobody computed.

The one exception is a metric that genuinely does not apply to a run: no primary
channel, no resume boundary. Those return no measurement and do not fail, because
nothing is broken.

**No default parameter values.** Callers pass everything explicitly. If that makes
a call site awkward, that is usually a sign the function is doing too much.

**Always use named arguments** when calling functions.

**Never return bare dicts.** Use a `NamedTuple` or a Pydantic model. Every FastAPI
endpoint declares a `response_model` and returns an instance of it.

**Documentation is read in two places**, and both have to work: in the repository
and on the [site](https://agencyenterprise.github.io/GlossoGen/). Write links
relative as you would for GitHub; `scripts/docs_hooks.py` rewrites the ones that
leave `docs/` into permalinks at build time. `make docs-build` runs `mkdocs build
--strict`, which fails on a link that would 404, and a CI job runs it on every PR.
`make docs-serve` previews locally.

**Notebooks are committed without their output**, which
`linter/check_notebook_outputs.py` checks and its `--strip` flag fixes. Output lives
inside the document, so running one and saving buries the next real diff under
regenerated cells.

**Prompts live in `prompts/*.jinja`**, and `linter/check_prompt_templates.py`
checks them: that each one parses, that its `{% include %}` targets are in the
directory the renderer searches, that nothing renders or includes it in vain, and
that every template name in shipped code answers to a file. Prompt-sized string
literals in scenario Python are reported as advisory.

**No inline imports** and **no `TYPE_CHECKING`** blocks, both enforced by
custom linters in `linter/`. If you hit a circular import, restructure rather than
working around it. Conditional loading of an optional dependency goes through
`importlib.import_module`, as in
[optional_ml_backend.py](src/glossogen/evaluation/metric_core/optional_ml_backend.py).

**Prompts live in Jinja templates**, never hardcoded in Python. They ship inside
the package, so a new `prompts/` directory needs no packaging change. A new
file *extension* does, via `[tool.setuptools.package-data]`. Rendering is strict:
a name the template uses but the caller never passes raises, because the
permissive default turns a typo into a prompt that is quietly missing a line.

**LLM output is parsed through a schema.** Define a Pydantic model, pass it to
`generate_structured()`, use the validated instance. Never parse free text.

**Docs describe the current state.** No "this now uses X instead of Y": the
reader does not know what Y was and does not care.

## Adding a scenario

Open a pull request with the scenario rather than an issue proposing one. A
scenario is self-contained, with its own package under
`src/glossogen/scenarios/<name>/`, touching no shared code.

[docs/creating-a-scenario.md](docs/creating-a-scenario.md) is the step-by-step
guide.

## Releases

Releases are cut by labelling a pull request with exactly one of `release:patch`,
`release:minor`, `release:major`, or `norelease`. New pull requests get
`release:patch` automatically. Change it if the work is a new feature, a breaking
change, or should not ship yet. A required check enforces that exactly one is set,
so merging always means something explicit.

Merging a labelled pull request runs `uv version --bump <label>`, commits the new
version, tags it `vX.Y.Z`, and publishes the backend and frontend images to GHCR.

**Do not edit `project.version` in `pyproject.toml` yourself.** The release commit
sets it. Keeping the bump and the tag in one automated step is what stops the two
drifting, which is what happened while it was a manual step.

Tagging `vX.Y.Z` by hand still publishes images, for the cases the label flow does
not cover.

## Costs

Running simulations spends real money against your own provider keys. Before
launching anything larger than a smoke test, read
[the cost model](docs/running-simulations.md#understanding-cost). A misconfigured
sweep is an expensive mistake and an easy one to make.

## Reporting bugs

Open an issue with the version or commit, what you expected, what happened, and
the relevant log lines. For anything security-related, follow
[SECURITY.md](SECURITY.md) instead, and do not open a public issue.
