# =============================================================================
# keiba-yosou Makefile
# =============================================================================
# One-command setup and common operations for the horse racing prediction system
#
# Usage:
#   make setup    - Initial setup (first time after clone)
#   make up       - Start all services
#   make down     - Stop all services
#   make logs     - View logs
#   make train    - Train/retrain the ML model
#   make health   - Check API health
# =============================================================================

.PHONY: setup build up down restart logs health train test clean help lint format typecheck docs docs-serve

# Default target
.DEFAULT_GOAL := help

# =============================================================================
# Setup Commands
# =============================================================================

## Initial setup after cloning the repository
setup: check-env
	@echo "============================================="
	@echo "  keiba-yosou Setup"
	@echo "============================================="
	@if [ ! -f .env ]; then \
		echo "[1/5] Creating .env from template..."; \
		cp .env.example .env; \
		echo "      Created .env file."; \
		echo "      IMPORTANT: Edit .env and fill in your credentials:"; \
		echo "        - DB_PASSWORD"; \
		echo "        - DISCORD_BOT_TOKEN"; \
		echo "        - DISCORD_NOTIFICATION_CHANNEL_ID"; \
		echo ""; \
	else \
		echo "[1/5] .env already exists, skipping..."; \
	fi
	@echo "[2/5] Building Docker images..."
	@docker compose build
	@echo "[3/5] Starting services..."
	@docker compose up -d
	@echo "[4/5] Waiting for API health check..."
	@sleep 5
	@$(MAKE) health --no-print-directory || echo "      API not ready yet. Check logs with: make logs"
	@echo "[5/5] Running database migrations..."
	@$(MAKE) migrate --no-print-directory || echo "      Migration failed. Check DB connection in .env"
	@echo ""
	@echo "============================================="
	@echo "  Setup complete!"
	@echo "============================================="
	@echo ""
	@echo "Next steps:"
	@echo "  1. Edit .env with your credentials (if not done)"
	@echo "  2. Restart services: make restart"
	@echo "  3. Train the model: make train"
	@echo "  4. Check API: make health"
	@echo ""
	@echo "Useful commands:"
	@echo "  make logs     - View container logs"
	@echo "  make down     - Stop all services"
	@echo "  make help     - Show all commands"
	@echo ""

## Check required tools are installed
check-env:
	@command -v docker >/dev/null 2>&1 || { echo "Error: docker is not installed"; exit 1; }
	@command -v docker compose >/dev/null 2>&1 || { echo "Error: docker compose is not installed"; exit 1; }

# =============================================================================
# Docker Commands
# =============================================================================

## Build Docker images
build:
	@echo "Building Docker images..."
	@docker compose build

## Start all services
up:
	@echo "Starting services..."
	@docker compose up -d
	@echo "Services started. Use 'make logs' to view logs."

## Stop all services
down:
	@echo "Stopping services..."
	@docker compose down

## Restart all services
restart:
	@echo "Restarting services..."
	@docker compose down
	@docker compose up -d
	@echo "Services restarted."

## View logs (all services)
logs:
	@docker compose logs -f

## View API logs only
logs-api:
	@docker compose logs -f api

## View Discord bot logs only
logs-bot:
	@docker compose logs -f discord-bot

## View ML trainer logs only
logs-ml:
	@docker compose logs -f ml-trainer

# =============================================================================
# Health & Status Commands
# =============================================================================

## Check API health
health:
	@echo "Checking API health..."
	@curl -sf http://localhost:8000/health > /dev/null && \
		echo "API is healthy" || \
		(echo "API is not responding. Check logs with: make logs-api" && exit 1)

## Show container status
status:
	@docker compose ps

# =============================================================================
# Database Commands
# =============================================================================

## Run database migrations (create required tables)
migrate:
	@echo "Running database migrations..."
	@docker compose exec ml-trainer python -m src.db.migrate
	@echo "Migrations complete."

## Check database tables
db-check:
	@echo "Checking database tables..."
	@docker compose exec ml-trainer python -m src.db.migrate --check

# =============================================================================
# ML Model Commands
# =============================================================================

## Train/retrain the ML model
train:
	@echo "Starting model training..."
	@echo "This may take 10-15 minutes."
	@docker compose exec ml-trainer python -m src.models.fast_train
	@echo "Training complete. Model saved to models/"

## Run model training in background
train-bg:
	@echo "Starting model training in background..."
	@docker compose exec -d ml-trainer python -m src.models.fast_train
	@echo "Training started. Check progress with: make logs-ml"

## Run weekly retrain process
retrain:
	@echo "Running weekly retrain process..."
	@docker compose exec ml-trainer python -m src.scheduler.weekly_retrain_model

## Collect race results
collect-results:
	@echo "Collecting race results..."
	@docker compose exec ml-trainer python -m src.scheduler.result_collector

# =============================================================================
# Development Commands
# =============================================================================

## Run tests
test:
	@echo "Running tests..."
	@DB_MODE=mock python -m pytest tests/ -v

## Run tests with coverage
test-cov:
	@echo "Running tests with coverage..."
	@DB_MODE=mock python -m pytest tests/ -v --cov=src --cov-report=html --cov-report=term-missing

## Run linter
lint:
	@echo "Running linter..."
	@ruff check src/

## Format code
format:
	@echo "Formatting code..."
	@black src/

## Type check
typecheck:
	@echo "Running type checker..."
	@mypy src/ --ignore-missing-imports

## Run all checks (lint + typecheck + test)
check: lint typecheck test
	@echo "All checks passed!"

## Run syntax check on all Python files
syntax-check:
	@echo "Checking Python syntax..."
	@find src -name "*.py" -exec python -m py_compile {} \;
	@echo "All syntax checks passed."

# =============================================================================
# Documentation Commands
# =============================================================================

## Build documentation
docs:
	@echo "Building documentation..."
	@mkdocs build

## Serve documentation locally
docs-serve:
	@echo "Serving documentation at http://localhost:8000..."
	@mkdocs serve

## Deploy documentation to GitHub Pages
docs-deploy:
	@echo "Deploying documentation..."
	@mkdocs gh-deploy

# =============================================================================
# Streamlit Commands
# =============================================================================

## Start Streamlit dashboard (local)
streamlit:
	@echo "Starting Streamlit dashboard..."
	@streamlit run streamlit/app.py --server.port 8501

## Start Streamlit dashboard (Docker)
streamlit-docker:
	@echo "Starting Streamlit in Docker..."
	@docker compose up -d streamlit
	@echo "Streamlit running at http://localhost:8501"

# =============================================================================
# Cleanup Commands
# =============================================================================

## Remove all containers and volumes
clean:
	@echo "Cleaning up..."
	@docker compose down -v --remove-orphans
	@echo "Cleanup complete."

## Remove Docker images
clean-images:
	@echo "Removing Docker images..."
	@docker compose down --rmi all
	@echo "Images removed."

# =============================================================================
# Help
# =============================================================================

## Show this help message
help:
	@echo "============================================="
	@echo "  keiba-yosou - Available Commands"
	@echo "============================================="
	@echo ""
	@echo "Setup:"
	@echo "  make setup          Initial setup (run after clone)"
	@echo "  make build          Build Docker images"
	@echo ""
	@echo "Services:"
	@echo "  make up             Start all services"
	@echo "  make down           Stop all services"
	@echo "  make restart        Restart all services"
	@echo "  make status         Show container status"
	@echo ""
	@echo "Logs:"
	@echo "  make logs           View all logs"
	@echo "  make logs-api       View API logs"
	@echo "  make logs-bot       View Discord bot logs"
	@echo "  make logs-ml        View ML trainer logs"
	@echo ""
	@echo "Health & Database:"
	@echo "  make health         Check API health"
	@echo "  make migrate        Run database migrations"
	@echo "  make db-check       Check if tables exist"
	@echo ""
	@echo "ML Model:"
	@echo "  make train          Train the ML model"
	@echo "  make train-bg       Train in background"
	@echo "  make retrain        Run weekly retrain"
	@echo "  make collect-results  Collect race results"
	@echo ""
	@echo "Development:"
	@echo "  make test           Run tests"
	@echo "  make test-cov       Run tests with coverage"
	@echo "  make lint           Run linter (ruff)"
	@echo "  make format         Format code (black)"
	@echo "  make typecheck      Type check (mypy)"
	@echo "  make check          Run all checks"
	@echo "  make syntax-check   Check Python syntax"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs           Build documentation"
	@echo "  make docs-serve     Serve docs locally"
	@echo "  make docs-deploy    Deploy to GitHub Pages"
	@echo ""
	@echo "Dashboard:"
	@echo "  make streamlit      Start Streamlit (local)"
	@echo "  make streamlit-docker  Start Streamlit (Docker)"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean          Remove containers and volumes"
	@echo "  make clean-images   Remove Docker images"
	@echo ""
