# FitTrack — common developer commands. Run `make help` for a list.
.DEFAULT_GOAL := help
SHELL := /bin/bash

BACKEND  := backend
FRONTEND := frontend

.PHONY: help install dev backend frontend lint format build reset-db

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Install backend (uv) and frontend (npm) dependencies; create .env files
	cd $(BACKEND) && uv sync
	cd $(FRONTEND) && npm install
	@test -f $(BACKEND)/.env || (cp $(BACKEND)/.env.example $(BACKEND)/.env && echo "Created backend/.env — add your GROQ_API_KEY")

dev: ## Run backend (:8010) and frontend (:5180) together; Ctrl+C stops both
	@trap 'kill 0' EXIT; \
	(cd $(BACKEND) && VIRTUAL_ENV= uv run genui) & \
	(cd $(FRONTEND) && npm run dev) & \
	wait

backend: ## Run only the FastAPI backend (auto-reload)
	cd $(BACKEND) && VIRTUAL_ENV= uv run genui

frontend: ## Run only the Vite dev server
	cd $(FRONTEND) && npm run dev

lint: ## Lint + type-check both apps
	cd $(BACKEND) && VIRTUAL_ENV= uv run ruff check src && VIRTUAL_ENV= uv run ruff format --check src && VIRTUAL_ENV= uv run mypy src
	cd $(FRONTEND) && npx tsc -b && npm run lint

format: ## Auto-format backend code
	cd $(BACKEND) && VIRTUAL_ENV= uv run ruff format src && VIRTUAL_ENV= uv run ruff check src --fix

build: ## Production build of the frontend (frontend/dist)
	cd $(FRONTEND) && npm run build

reset-db: ## Delete the local SQLite DB (demo data is re-seeded on next start)
	rm -f $(BACKEND)/fittrack.db
