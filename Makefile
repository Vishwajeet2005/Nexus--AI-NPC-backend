.PHONY: help up down logs restart migrate lint format build

help:
	@echo "Nexus Developer Commands:"
	@echo "  make up         - Start all services (detached)"
	@echo "  make down       - Stop and remove all services"
	@echo "  make logs       - Follow logs for all services"
	@echo "  make restart    - Restart the API container"
	@echo "  make migrate    - Run Alembic migrations against the database"
	@echo "  make lint       - Run ruff linter"
	@echo "  make format     - Run ruff formatter"
	@echo "  make build      - Rebuild the API container image"

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

restart:
	docker compose restart api

migrate:
	docker compose exec api alembic upgrade head

lint:
	ruff check .

format:
	ruff format .

build:
	docker compose build
