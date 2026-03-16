# Installation
install:
	@echo "Installing dependencies..."
	VIRTUAL_ENV= uv sync
	@echo "Dependencies installed"

# Linting
lint:
	@echo "Linting..."
	VIRTUAL_ENV= uv run --no-sync black . --exclude '\.venv'
	VIRTUAL_ENV= uv run --no-sync isort . --skip-glob '.venv/*'
	VIRTUAL_ENV= uv run --no-sync ruff check . --exclude .venv
	VIRTUAL_ENV= uv run --no-sync mypy . --exclude '^\.venv'
	VIRTUAL_ENV= uv run --no-sync pyright --project pyproject.toml
	VIRTUAL_ENV= uv run --no-sync vulture src/ --min-confidence 70
	VIRTUAL_ENV= uv run --no-sync python linter/check_inline_imports.py --target-dir .
	VIRTUAL_ENV= uv run --no-sync python linter/check_type_checking.py --target-dir .
	@echo "Linting complete"

.PHONY: install lint
