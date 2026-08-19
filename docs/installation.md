# Installation

Two ways in, depending on what you are doing.

- **Working on glossogen itself** — clone the repository and follow this page.
- **Using glossogen from your own project**, to write a scenario or a metric in
  your own package: skip to [As a dependency](#as-a-dependency).

## Prerequisites

- **Python 3.12**
- **Node.js ≥ 22**, for the frontend
- **[uv](https://docs.astral.sh/uv/)**, the Python package manager
- **make**, **git**
- **System libraries for weasyprint** (PDF export). macOS:
  `brew install pango cairo gdk-pixbuf libffi`. Debian/Ubuntu:
  `apt-get install libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0`.
- **Postgres ≥ 14**, optional. Leave `DATABASE_URL` unset for no-database local
  mode: the runs index is derived from the `runs/` directory and OAuth state is
  held in memory. See [Local Postgres](#local-postgres-optional).
- **Docker + Docker Compose**, optional. Needed for the local
  [Langfuse stack](../README.md#observability) and for
  [`docker compose up`](deployment.md#self-hosting-with-docker-compose).

## Install dependencies

```bash
make install            # backend and frontend
make install-server     # backend only (uv sync)
make install-frontend   # frontend only (npm ci)
```

If you intend to run evaluations, install the ML extra as well:

```bash
make install-metrics    # everything above, plus the metrics-ml extra
```

This is the setup for research use. It is a separate target because the extra
pulls in torch and transformers, several gigabytes that a server which only
browses runs never executes. Deployments therefore install without it, which is
why it is not the default.

### Optional extras

| Extra | Install | Needed for |
|---|---|---|
| `metrics-ml` | `uv sync --extra metrics-ml` | `perplexity` and the English n-gram surprisal metrics (torch + transformers) |
| `evals` | `uv sync --extra evals` | The veyru judge-accuracy harness (`inspect-ai`) |

These metrics depend on `metrics-ml`:

| Metric | Needs | Without the extra |
|---|---|---|
| `perplexity` | `torch`, `minicons` | **Fails** |
| `english_ngram_surprisal` | `datasets` | Runs from a cached model; **fails** only when the cache is cold |
| `english_ngram_backoff_surprisal` | `datasets` | Same |

The n-gram metrics train a character trigram from wikitext once and cache it
under `~/.cache/glossogen/`. After that first build they need no ML dependency at
all, so copying a warm cache is an alternative to installing the extra.

**Requesting a metric that cannot run is an error, not a skip.** Evaluation exits
non-zero with a message naming the missing package and the install command. The
report is written first, so results from the metrics that did succeed are never
lost: you get partial results *and* a failure signal.

A metric that quietly produced nothing would be indistinguishable from a run with
nothing to measure, which is how a broken environment gets mistaken for a valid
result. The same applies to a metric that raises for any other reason: evaluation
runs the rest, writes the report, then exits non-zero. Skipping is reserved for
metrics that genuinely do not apply to a run, such as `perplexity` on a scenario
with no primary channel. See [Evaluation](evaluation.md#when-a-metric-produces-nothing).

The `evals` extra backs a standalone script at
`src/glossogen/scenarios/veyru/evals/` rather than a registered metric, so
without it that script fails with a plain `ModuleNotFoundError`.
`make install-server` includes it, since type checking needs it.

## Configure environment

```bash
cp .env.example .env
```

At minimum, set `ANTHROPIC_API_KEY`. `.env.example` documents every variable
(provider keys, authentication, CORS, runs directory, log level) and pre-fills
the local Langfuse keys, so copying it as-is enables tracing once you run
`make langfuse-up`. Blank both `LANGFUSE_*` keys to disable telemetry.

Every command reads the nearest `.env` at or above the directory it runs in, so
the repo root's file is found from anywhere inside the checkout. A variable
already set in the environment wins over the file, which is what lets one
command override it: `LOG_LEVEL=DEBUG glossogen evaluate ...`.

Leave `DATABASE_URL` unset for no-database local mode.

## Local Postgres (optional)

Set up Postgres only if you want the Postgres-backed runs index locally, or to
run multi-tenant auth. Create a role, a database owned by that role, and
point the backend at it.

```bash
# 1. Create a Postgres role (one-time). On macOS/Homebrew a superuser role named
#    after your OS user already exists, so you can skip this and connect without
#    credentials. On Debian/Ubuntu (peer auth), create a role first:
sudo -u postgres createuser --createdb --pwprompt glossogen   # prompts for a password

# 2. Create the database owned by that role (one-time).
createdb -O glossogen glossogen_dev
# Homebrew default-role shortcut (role == your OS user, no password): createdb glossogen_dev

# 3. Apply the migrations (groups, runs, user_last_active_group, and the OAuth tables).
DATABASE_URL=postgresql://glossogen:<password>@localhost:5432/glossogen_dev \
  VIRTUAL_ENV= uv run --no-sync alembic upgrade head

# 4. Verify the schema.
psql -d glossogen_dev -c "\dt"
```

### Upgrading a database you already have

The step above is written for a database being created. An existing one needs the same
command again after any pull that adds a migration, and nothing reminds you: the server
does not migrate on startup, so the first sign is a failure at boot naming a column that
does not exist.

```bash
DATABASE_URL=postgresql://localhost:5432/glossogen_dev \
  VIRTUAL_ENV= uv run --no-sync alembic upgrade head
```

`alembic` reads `DATABASE_URL` from the environment and does not load `.env`, which the
server does load. So a value that works for `make dev` still has to be passed here
explicitly. Deployed images have it in their environment already and run
`alembic upgrade head` before serving, which is why this only bites locally.

`DATABASE_URL` is `postgresql://<user>:<password>@<host>:<port>/<db>`. On a
Homebrew install where the role matches your OS user and local connections use
`trust`/`peer` auth, drop the credentials entirely:
`postgresql://localhost:5432/glossogen_dev`.

The first backend boot auto-creates the synthetic `local` group used in
single-tenant mode. Install no identity provider and every request runs as
`local-user` inside that group.

To reset:
`dropdb glossogen_dev && createdb -O glossogen glossogen_dev && alembic upgrade head`.

## As a dependency

glossogen is not published to PyPI, so install from the repository, pinning a
tag. Replace `<tag>` with a release from
[the releases page](https://github.com/agencyenterprise/GlossoGen/releases):

```bash
pip install "git+https://github.com/agencyenterprise/GlossoGen.git@<tag>"
# or, with uv:
uv add "glossogen @ git+https://github.com/agencyenterprise/GlossoGen.git@<tag>"
```

In a `pyproject.toml`, the same thing as a PEP 508 direct reference:

```toml
[project]
dependencies = [
    "glossogen @ git+https://github.com/agencyenterprise/GlossoGen.git@<tag>",
]
```

Pick a release that carries the plug-in entry points, which arrived after
`v0.1.16`. Earlier tags have no `glossogen.scenarios.v1` group, so a scenario
declared under it would be installed and never read. Pin a tag rather than
tracking `main`, and swap it for a branch or commit SHA to track unreleased work.

The scenario contract carries a version in the entry-point group a plug-in
declares itself under, so a platform that has moved on reports the mismatch
rather than running your scenario against a contract it was not written for.

Installing brings the `glossogen` command with it, so `glossogen run ...` and
`glossogen evaluate ...` work without `python -m`. The web UI comes from the same
command: `glossogen serve --runs-dir ./runs --port 8000 --ui-port 3000` serves
the API and starts the published frontend image against it, which needs Docker
but no checkout. See
[Viewing your runs in the web UI](creating-a-scenario.md#viewing-your-runs-in-the-web-ui).

### Configuring it

The `.env` goes in **your** project, beside your `pyproject.toml`, not in a
glossogen checkout you do not have. Commands read the nearest one at or above
the directory they run in, so a command run from a subdirectory still finds it:

```
my-scenarios/
├── .env             # ANTHROPIC_API_KEY=...
├── pyproject.toml
├── runs/            # --runs-dir points here
└── src/my_scenarios/...
```

`ANTHROPIC_API_KEY` is the one variable a run cannot do without. The others are
optional and all documented in
[`.env.example`](https://github.com/agencyenterprise/GlossoGen/blob/main/.env.example);
`DATABASE_URL` in particular should stay unset unless you want the
Postgres-backed runs index, since with it set the run list is a database table
rather than the directory you pointed `--runs-dir` at. Anything already in the
environment wins over the file.

From there, start a scenario by generating one:

```bash
glossogen new-scenario reactor_purge --target-dir .
```

That writes a package that already runs, pinned to the glossogen you have
installed. See [Creating a scenario](creating-a-scenario.md) for what it wrote
and what to change first, [Testing a scenario](testing-a-scenario.md) for the
harness its tests use, and [Creating a metric](creating-a-metric.md) for the
other half. All three cover shipping in your own package.
