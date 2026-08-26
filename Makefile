# Installation
install: install-server install-frontend

# --extra evals is required for type checking: judge_accuracy_eval.py imports
# inspect_ai at module scope, and without the package pyright reports every
# symbol in that file as unknown. Extras are separate from dependency-groups
# in uv, so --all-groups does not cover it.
#
# --extra metrics-ml is deliberately omitted: it is multi-gigabyte, and nothing
# under src/ imports torch, minicons, or datasets directly (see
# evaluation/metric_core/optional_ml_backend.py), so pyright does not need it.
# `--group dev` rather than `--all-groups`: the `notebooks` group carries jupyter,
# pandas and matplotlib for the examples under notebooks/, and neither a dev
# install nor the test suite needs any of it. Use `make install-notebooks` for that.
install-server:
	@echo "Installing server dependencies..."
	VIRTUAL_ENV= uv sync --group dev --extra evals
	@echo "Server dependencies installed"

# Recommended for research use: adds the metrics-ml extra so `perplexity` and
# the English n-gram surprisal metrics can run. Kept separate from
# install-server because torch + transformers are several gigabytes and a
# deployment that only serves runs never executes them.
install-metrics:
	@echo "Installing server dependencies with the metrics-ml extra..."
	VIRTUAL_ENV= uv sync --group dev --extra evals --extra metrics-ml
	@echo "Server dependencies installed (metrics-ml enabled)"

# The example notebooks. They generate their own run with scripted agents or read
# CSVs committed under notebooks/data/, so they need no API key and reach no
# network, which is what lets CI execute them.
install-notebooks:
	@echo "Installing notebook dependencies..."
	VIRTUAL_ENV= uv sync --group dev --group notebooks --extra evals
	@echo "Notebook dependencies installed"

# Executes every notebook top to bottom and fails on the first cell that raises.
test-notebooks:
	@echo "Running notebooks..."
	VIRTUAL_ENV= uv run --no-sync python -m pytest --nbmake notebooks/ -q
	@echo "Notebooks complete"

# The documentation site.
install-docs:
	@echo "Installing docs dependencies..."
	VIRTUAL_ENV= uv sync --group dev --group docs --group notebooks --extra evals
	@echo "Docs dependencies installed"

# mkdocs comes from the docs dependency group, which plain `make install` skips.
check-mkdocs:
	@VIRTUAL_ENV= uv run --no-sync python -c "import mkdocs" 2>/dev/null || \
		{ echo "mkdocs is not installed: run 'make install-docs' first"; exit 1; }

# --strict fails the build on a link that would 404 on the site. The docs are
# written to be read in the repository, where a link into src/ resolves and on a
# site does not, so this is the check that keeps the two readings honest.
docs-build: check-mkdocs
	VIRTUAL_ENV= uv run --no-sync mkdocs build --strict

docs-serve: check-mkdocs
	VIRTUAL_ENV= uv run --no-sync mkdocs serve

install-frontend:
	cd frontend && npm ci

# Linting

# -n auto spreads the suite over every core. The integration tests are sleep-
# bound rather than CPU-bound (they wait on a real MCP server and the game
# clock's timing floors), so running them alongside each other costs nothing and
# is where most of the saving comes from.
#
# --dist loadgroup keeps tests marked with the same xdist_group on one worker.
# tests/metrics shares a single simulated run across every metric file; spread
# over workers, each would build its own and the parallel run would cost more
# simulations than the serial one.
test:
	@echo "Running tests..."
	VIRTUAL_ENV= uv run --no-sync python -m pytest tests/ -q -n auto --dist loadgroup
	@echo "Tests complete"

# Tracing every import roughly triples a worker's startup, so `test` stays lean
# and CI runs this one. It writes .coverage, which the PR comment action reads
# to work out how well the diff is covered. pytest-cov combines the per-worker
# data files itself, so the parallel total matches the serial one.
test-cov:
	@echo "Running tests with coverage..."
	VIRTUAL_ENV= uv run --no-sync python -m pytest tests/ -q -n auto --cov --cov-report=term-missing:skip-covered
	@echo "Coverage complete"

# Same data as test-cov, rendered as a browsable report at htmlcov/index.html.
coverage-html: test-cov
	VIRTUAL_ENV= uv run --no-sync coverage html
	@echo "Open htmlcov/index.html"

lint: lint-server lint-frontend
	@echo "All linting complete"

lint-server:
	@echo "Linting server..."
	VIRTUAL_ENV= uv run --no-sync black . --exclude '\.venv|frontend|vulture_whitelist\.py|runs'
	VIRTUAL_ENV= uv run --no-sync isort . --skip-glob '.venv/*' --skip-glob 'frontend/*' --skip-glob 'vulture_whitelist.py' --skip-glob 'runs/*'
	VIRTUAL_ENV= uv run --no-sync ruff check . --exclude .venv --exclude frontend --exclude vulture_whitelist.py --exclude runs
	VIRTUAL_ENV= uv run --no-sync pyright --project pyproject.toml
	VIRTUAL_ENV= uv run --no-sync vulture src/ scripts/ linter/ vulture_whitelist.py --min-confidence 60
	VIRTUAL_ENV= uv run --no-sync python linter/check_inline_imports.py --target-dir . --exclude runs --exclude modal
	VIRTUAL_ENV= uv run --no-sync python linter/check_type_checking.py --target-dir . --exclude runs
	VIRTUAL_ENV= uv run --no-sync python linter/check_prompt_templates.py --target-dir . --exclude runs --exclude modal --exclude build --exclude node_modules
	VIRTUAL_ENV= uv run --no-sync python linter/check_notebook_outputs.py --target-dir . --exclude runs --exclude site --exclude build --exclude node_modules --exclude .venv
	@echo "Server linting complete"

# CI mode for the server: same checks as lint-server, but black and isort only
# report. lint-server rewrites files, which in CI means it fixes the ephemeral
# checkout and exits 0 — so formatting drift was structurally uncatchable.
check-server:
	@echo "Checking server..."
	VIRTUAL_ENV= uv run --no-sync black --check . --exclude '\.venv|frontend|vulture_whitelist\.py|runs'
	VIRTUAL_ENV= uv run --no-sync isort --check-only . --skip-glob '.venv/*' --skip-glob 'frontend/*' --skip-glob 'vulture_whitelist.py' --skip-glob 'runs/*'
	VIRTUAL_ENV= uv run --no-sync ruff check . --exclude .venv --exclude frontend --exclude vulture_whitelist.py --exclude runs
	VIRTUAL_ENV= uv run --no-sync pyright --project pyproject.toml
	VIRTUAL_ENV= uv run --no-sync vulture src/ scripts/ linter/ vulture_whitelist.py --min-confidence 60
	VIRTUAL_ENV= uv run --no-sync python linter/check_inline_imports.py --target-dir . --exclude runs --exclude modal
	VIRTUAL_ENV= uv run --no-sync python linter/check_type_checking.py --target-dir . --exclude runs
	VIRTUAL_ENV= uv run --no-sync python linter/check_prompt_templates.py --target-dir . --exclude runs --exclude modal --exclude build --exclude node_modules
	VIRTUAL_ENV= uv run --no-sync python linter/check_notebook_outputs.py --target-dir . --exclude runs --exclude site --exclude build --exclude node_modules --exclude .venv
	@echo "Server check complete"

lint-frontend:
	@echo "Linting frontend..."
	cd frontend && npx prettier --write "src/**/*.{ts,tsx,js,jsx,json,css,scss,md}"
	cd frontend && npx eslint src/ --max-warnings 0
	cd frontend && npx stylelint "src/**/*.css" --allow-empty-input
	cd frontend && npx tsc --noEmit
	cd frontend && npm test
	@echo "Frontend linting complete"

check-frontend:
	@echo "Checking frontend..."
	cd frontend && npx prettier --check "src/**/*.{ts,tsx,js,jsx,json,css,scss,md}"
	cd frontend && npx eslint src/ --max-warnings 0
	cd frontend && npx stylelint "src/**/*.css" --allow-empty-input
	cd frontend && npm test
	cd frontend && npx tsc --noEmit
	@echo "Frontend check complete"

# Development
dev:
	VIRTUAL_ENV= uv run -m uvicorn glossogen.server.app:app --reload --reload-dir src

dev-frontend:
	cd frontend && npm run dev

# Local self-hosted Langfuse observability stack (traces from `glossogen run`).
# --env-file /dev/null keeps glossogen's own .env from leaking into the Langfuse
# stack's variable substitution. First boot takes ~2-3 min; UI at :3001
# (3000 is the frontend dev server).
langfuse-up:
	docker compose --env-file /dev/null -f docker-compose.langfuse.yml up -d
	@echo "Langfuse starting at http://localhost:3001 (first boot ~2-3 min)."
	@echo "Login: local@glossogen.dev / local-dev-password  |  keys pre-seeded in .env.example"

langfuse-down:
	docker compose --env-file /dev/null -f docker-compose.langfuse.yml down

langfuse-logs:
	docker compose --env-file /dev/null -f docker-compose.langfuse.yml logs -f langfuse-web

# API types
export-openapi:
	VIRTUAL_ENV= uv run python scripts/export_openapi.py > frontend/openapi.json

gen-api-types: export-openapi
	cd frontend && npx openapi-typescript openapi.json --output src/types/api.gen.ts
	cd frontend && npx prettier --write src/types/api.gen.ts

.PHONY: install install-server install-metrics install-notebooks install-docs install-frontend lint lint-server check-server lint-frontend check-frontend dev dev-frontend langfuse-up langfuse-down langfuse-logs export-openapi gen-api-types test test-cov test-notebooks coverage-html check-mkdocs docs-build docs-serve
