# Installation
install: install-server install-frontend

install-server:
	@echo "Installing server dependencies..."
	VIRTUAL_ENV= uv sync --all-groups
	@echo "Server dependencies installed"

install-frontend:
	cd frontend && npm ci

# Linting
lint: lint-server lint-frontend
	@echo "All linting complete"

lint-server:
	@echo "Linting server..."
	VIRTUAL_ENV= uv run --no-sync black . --exclude '\.venv|frontend|vulture_whitelist\.py|runs'
	VIRTUAL_ENV= uv run --no-sync isort . --skip-glob '.venv/*' --skip-glob 'frontend/*' --skip-glob 'vulture_whitelist.py' --skip-glob 'runs/*'
	VIRTUAL_ENV= uv run --no-sync ruff check . --exclude .venv --exclude frontend --exclude vulture_whitelist.py --exclude runs
	VIRTUAL_ENV= uv run --no-sync pyright --project pyproject.toml
	VIRTUAL_ENV= uv run --no-sync vulture src/ vulture_whitelist.py --min-confidence 60
	VIRTUAL_ENV= uv run --no-sync python linter/check_inline_imports.py --target-dir . --exclude runs --exclude modal --exclude scripts
	VIRTUAL_ENV= uv run --no-sync python linter/check_type_checking.py --target-dir . --exclude runs --exclude scripts
	@echo "Server linting complete"

lint-frontend:
	@echo "Linting frontend..."
	cd frontend && npx prettier --write "src/**/*.{ts,tsx,js,jsx,json,css,scss,md}"
	cd frontend && npx eslint src/ --max-warnings 0
	cd frontend && npx stylelint "src/**/*.css" --allow-empty-input
	cd frontend && npx tsc --noEmit
	@echo "Frontend linting complete"

check-frontend:
	@echo "Checking frontend..."
	cd frontend && npx prettier --check "src/**/*.{ts,tsx,js,jsx,json,css,scss,md}"
	cd frontend && npx eslint src/ --max-warnings 0
	cd frontend && npx stylelint "src/**/*.css" --allow-empty-input
	cd frontend && npx tsc --noEmit
	@echo "Frontend check complete"

# Development
dev:
	GLOSSOGEN_RUNS_DIR=./runs VIRTUAL_ENV= uv run -m uvicorn glossogen.server.app:app --reload --reload-dir src

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

.PHONY: install install-server install-frontend lint lint-server lint-frontend check-frontend dev dev-frontend langfuse-up langfuse-down langfuse-logs export-openapi gen-api-types
