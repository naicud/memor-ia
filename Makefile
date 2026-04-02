.DEFAULT_GOAL := help
PYTHON := python3

# ─── Setup ───────────────────────────────────────────────────────────

.PHONY: install
install: ## Install with uv (core + mcp)
	uv pip install -e ".[mcp]"

.PHONY: install-dev
install-dev: ## Install with dev + test deps
	uv pip install -e ".[mcp,test,dev]"

.PHONY: install-full
install-full: ## Install everything (including graph backend)
	uv pip install -e ".[all]"

.PHONY: venv
venv: ## Create virtual environment with uv
	uv venv .venv
	@echo "Run: source .venv/bin/activate"

# ─── Quality ─────────────────────────────────────────────────────────

.PHONY: test
test: ## Run test suite
	$(PYTHON) -m pytest tests/ -q

.PHONY: test-verbose
test-verbose: ## Run tests with verbose output
	$(PYTHON) -m pytest tests/ -v --tb=short

.PHONY: test-e2e
test-e2e: ## Run E2E backend tests (local, no FalkorDB)
	$(PYTHON) -m pytest tests/test_e2e_backends.py -v --tb=short

.PHONY: test-e2e-full
test-e2e-full: ## Run E2E with FalkorDB (requires: docker compose up falkordb)
	MEMORIA_GRAPH_HOST=localhost $(PYTHON) -m pytest tests/test_e2e_backends.py -v --tb=short

.PHONY: test-cov
test-cov: ## Run tests with coverage
	$(PYTHON) -m pytest tests/ --cov=memoria --cov-report=term-missing

.PHONY: lint
lint: ## Run ruff linter
	ruff check src/ tests/

.PHONY: lint-fix
lint-fix: ## Auto-fix linting issues
	ruff check --fix src/ tests/

.PHONY: typecheck
typecheck: ## Run mypy type checking
	mypy src/memoria/

.PHONY: check
check: lint typecheck test ## Run all quality checks

# ─── MCP Server ──────────────────────────────────────────────────────

.PHONY: serve
serve: ## Start MCP server (stdio — for Claude Desktop/Cursor)
	$(PYTHON) -m memoria.mcp

.PHONY: serve-http
serve-http: ## Start MCP server (HTTP on port 8080)
	MEMORIA_TRANSPORT=http MEMORIA_PORT=8080 $(PYTHON) -m memoria.mcp

# ─── Docker ──────────────────────────────────────────────────────────

.PHONY: docker-build
docker-build: ## Build Docker image
	docker build -t memoria-mcp .

.PHONY: docker-run
docker-run: ## Run MCP server in Docker
	docker run -p 8080:8080 --rm memoria-mcp

.PHONY: docker-up
docker-up: ## Start with docker-compose
	docker compose up -d

.PHONY: docker-down
docker-down: ## Stop docker-compose
	docker compose down

# ─── Package ─────────────────────────────────────────────────────────

.PHONY: build
build: ## Build distribution package
	uv build

.PHONY: clean
clean: ## Clean build artifacts
	rm -rf dist/ build/ *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ─── Help ────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
