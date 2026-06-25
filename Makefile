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

results-viewer:
	VIRTUAL_ENV= PYTHONPATH=. uv run --group analysis --no-sync streamlit run analysis/results_viewer/app.py

# Google Sheets sync — regenerate each workbook, then overwrite only its data tabs
# (chart tabs untouched; a pre-write CSV backup lands under analysis/sheets_sync/backups/).
sync-sheets-baseline:
	VIRTUAL_ENV= uv run --no-sync --with openpyxl python -m analysis.baseline_round_success.export_baseline_round_success
	VIRTUAL_ENV= PYTHONPATH=. uv run --no-sync --group sheets python analysis/sheets_sync/sync_to_sheets.py --target baseline

sync-sheets-noise:
	VIRTUAL_ENV= uv run --no-sync --with openpyxl python -m analysis.channel_noise_export.export_channel_noise
	VIRTUAL_ENV= PYTHONPATH=. uv run --no-sync --group sheets python analysis/sheets_sync/sync_to_sheets.py --target channel_noise

sync-sheets-protocol:
	VIRTUAL_ENV= uv run --no-sync --with openpyxl python -m analysis.protocol_learnability_export.export_protocol_learnability
	VIRTUAL_ENV= PYTHONPATH=. uv run --no-sync --group sheets python analysis/sheets_sync/sync_to_sheets.py --target protocol_learnability

sync-sheets: sync-sheets-baseline sync-sheets-noise sync-sheets-protocol
	@echo "All spreadsheets synced"

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
	SCHMIDT_RUNS_DIR=./runs VIRTUAL_ENV= uv run -m uvicorn schmidt.server.app:app --reload --reload-dir src

dev-frontend:
	cd frontend && npm run dev

# API types
export-openapi:
	VIRTUAL_ENV= uv run python scripts/export_openapi.py > frontend/openapi.json

gen-api-types: export-openapi
	cd frontend && npx openapi-typescript openapi.json --output src/types/api.gen.ts
	cd frontend && npx prettier --write src/types/api.gen.ts

.PHONY: install install-server install-frontend lint lint-server lint-frontend check-frontend dev dev-frontend results-viewer sync-sheets sync-sheets-baseline sync-sheets-noise sync-sheets-protocol export-openapi gen-api-types
