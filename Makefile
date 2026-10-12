.PHONY: help install install-ocr install-chain install-dev db-up db-down migrate revision test lint format run

help:
	@echo "install      - create venv and install backend deps"
	@echo "install-dev  - install dev/test extras into venv"
	@echo "install-ocr  - install PaddleOCR/pdfplumber extras (heavy)"
	@echo "install-chain - install web3 extra for Polygon anchoring"
	@echo "db-up        - start Postgres via docker compose"
	@echo "db-down      - stop docker compose stack"
	@echo "migrate      - apply Alembic migrations"
	@echo "revision     - autogenerate a migration (make revision m=\"message\")"
	@echo "run          - run the API locally with reload"
	@echo "test         - run pytest with coverage"
	@echo "lint         - ruff check + format check"
	@echo "format       - ruff format + fix"

install:
	python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'

install-dev:
	pip install -e '.[dev]'

install-ocr:
	pip install -e '.[ocr]'

install-chain:
	pip install -e '.[chain]'

db-up:
	docker compose up -d db

db-down:
	docker compose down

migrate:
	cd backend && alembic upgrade head

revision:
	cd backend && alembic revision --autogenerate -m "$(m)"

run:
	cd backend && uvicorn app.main:app --reload --port 8000

test:
	cd backend && pytest --cov=app --cov-report=term-missing

lint:
	cd backend && ruff check app tests && ruff format --check app tests

format:
	cd backend && ruff format app tests && ruff check --fix app tests