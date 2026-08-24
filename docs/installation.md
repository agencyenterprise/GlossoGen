# Installation

Two ways in. To write a scenario or a metric in a package of your own, install
glossogen as a dependency. To work on the platform itself, clone the repository
and start at [Working on glossogen itself](#working-on-glossogen-itself).

## As a dependency

glossogen needs Python 3.12, and the project you install it into has to allow
that: a `requires-python` of at least 3.12, and in a uv project
`uv python pin 3.12`. On a project pinned lower, the install fails with a
resolution error naming the conflict.

glossogen is not published to PyPI, so install from the repository, pinning a tag.
Replace `<tag>` with a release from
[the releases page](https://github.com/agencyenterprise/GlossoGen/releases):

```bash
uv add "glossogen @ git+https://github.com/agencyenterprise/GlossoGen.git@<tag>"
# or, with pip:
pip install "git+https://github.com/agencyenterprise/GlossoGen.git@<tag>"
```

In a `pyproject.toml`, the same thing as a PEP 508 direct reference:

```toml
[project]
dependencies = [
    "glossogen @ git+https://github.com/agencyenterprise/GlossoGen.git@<tag>",
]
```

Pin a tag after `v0.1.16`. Earlier ones have no `glossogen.scenarios.v1`
entry-point group, so a scenario declaring itself under it would be installed and
never read. A branch or a commit SHA works in the same place for tracking
unreleased work. The group name carries the contract version, so a platform that
has moved on reports the mismatch instead of running your scenario against a
contract it was not written for.

Two extras matter here: `glossogen[testing]` adds the pytest harness
[Testing a scenario](testing-a-scenario.md) uses, and `glossogen[metrics-ml]`
adds the torch backend behind `perplexity` and the n-gram surprisal metrics.

Installing brings the `glossogen` command, so `glossogen run ...` and
`glossogen evaluate ...` work without `python -m`. The web UI comes from the same
command: `glossogen serve --runs-dir ./runs --port 8000 --ui-port 3000` serves the
API and starts the published frontend image against it, which needs Docker but no
checkout. See
[Viewing your runs in the web UI](creating-a-scenario.md#viewing-your-runs-in-the-web-ui).

## Configure environment

The `.env` goes in the project you run commands from. From a clone, copy the
template:

```bash
cp .env.example .env
```

An install from a package has no local template, so start from
[`.env.example` on GitHub](https://github.com/agencyenterprise/GlossoGen/blob/main/.env.example).
Commands read the nearest `.env` at or above the directory they run in, so a
command run from a subdirectory still finds it:

```
my-scenarios/
├── .env             # provider API keys
├── pyproject.toml
├── runs/            # --runs-dir points here
└── src/my_scenarios/...
```

A run needs a key for every provider its agents and its judge resolve to. The
shipped presets use an Anthropic judge wherever a scenario has one, so those need
`ANTHROPIC_API_KEY`.
`.env.example` documents every variable (provider keys, authentication, CORS,
runs directory, log level) and pre-fills the local Langfuse keys, so a clone that copies it as-is
traces once `make langfuse-up` runs. Blank both `LANGFUSE_*` keys to disable
telemetry.

Keep `DATABASE_URL` unset unless you want the Postgres-backed runs index, because
with it set the run list is a database table rather than the directory
`--runs-dir` points at. A variable already set in the environment wins over the
file, which is what lets one command override it:
`LOG_LEVEL=DEBUG glossogen evaluate ...`.

## Tracing from your own project

The local Langfuse stack runs from a compose file this repository carries, which a
wheel does not. Fetch that one file, pinned to the tag you installed:

```bash
curl -O https://raw.githubusercontent.com/agencyenterprise/GlossoGen/<tag>/docker-compose.langfuse.yml
docker compose --env-file /dev/null -f docker-compose.langfuse.yml up -d
```

`--env-file /dev/null` keeps your own `.env` out of the compose file's variable
substitution, which is what `make langfuse-up` does too. Then put the seeded keys
in your `.env`, since you have no `.env.example` of ours to copy:

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-local-dev
LANGFUSE_SECRET_KEY=sk-lf-local-dev
LANGFUSE_HOST=http://localhost:3001
```

[Observability](observability.md) has what the stack records and when it
is on.

## Working on glossogen itself

Clone the repository, then:

### Prerequisites

| Requirement | Needed for |
|---|---|
| Python 3.12, [uv](https://docs.astral.sh/uv/), make, git | Everything |
| Node.js ≥ 22 | The frontend |
| Pango, Cairo, gdk-pixbuf, libffi | PDF export via weasyprint. macOS: `brew install pango cairo gdk-pixbuf libffi`. Debian/Ubuntu: `apt-get install libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0` |
| Postgres ≥ 14 | Optional. Unset `DATABASE_URL` for no-database local mode: the runs index comes from the `runs/` directory and OAuth state is held in memory. See [Local Postgres](#local-postgres-optional) |
| Docker + Docker Compose | Optional. The local [Langfuse stack](observability.md), [`docker compose up`](deployment.md#self-hosting-with-docker-compose), and the `--ui-port` flag on `glossogen serve` |

### Install dependencies

| Command | Installs |
|---|---|
| `make install` | Backend and frontend |
| `make install-server` | Backend only (`uv sync --group dev --extra evals`) |
| `make install-frontend` | Frontend only (`npm ci`) |
| `make install-metrics` | Backend plus the `metrics-ml` extra |

`make install-metrics` is what research use needs. It is a separate target because
the extra pulls torch and transformers, several gigabytes that a server which only
browses runs never executes, so deployments install without it.

### Optional extras

| Extra | Install | Needed for |
|---|---|---|
| `metrics-ml` | `uv sync --extra metrics-ml` | `perplexity` and the English n-gram surprisal metrics (torch + transformers) |
| `evals` | `uv sync --extra evals` | The veyru judge-accuracy harness (`inspect-ai`). `make install-server` includes it, since type checking needs it |

| Metric | Needs | Without the extra |
|---|---|---|
| `perplexity` | `torch`, `minicons` | **Fails** |
| `english_ngram_surprisal` | `datasets` | Runs from a cached model; **fails** only when the cache is cold |
| `english_ngram_backoff_surprisal` | `datasets` | Same |

The n-gram metrics train a character trigram from wikitext once and cache it under
`~/.cache/glossogen/`. After that first build they need no ML dependency at all, so
copying a warm cache is an alternative to installing the extra.

**A metric that cannot run fails the evaluation rather than skipping.** Evaluation writes
the report first, then exits non-zero naming the missing package and its install
command, so the metrics that did succeed are never lost.
[Evaluation](evaluation.md#when-a-metric-produces-nothing) has the rule and the
cases where a skip is the right answer.

With dependencies installed, [configure the environment](#configure-environment).

## Local Postgres (optional)

Only for the Postgres-backed runs index locally, or for multi-tenant auth.

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

`DATABASE_URL` is `postgresql://<user>:<password>@<host>:<port>/<db>`. On a Homebrew
install where the role matches your OS user and local connections use `trust`/`peer`
auth, drop the credentials entirely: `postgresql://localhost:5432/glossogen_dev`.

The first backend boot auto-creates the synthetic `local` group used in
single-tenant mode. Install no identity provider and every request runs as
`local-user` inside that group.

To reset:
`dropdb glossogen_dev && createdb -O glossogen glossogen_dev && alembic upgrade head`.
