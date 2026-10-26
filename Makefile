VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
RUFF := $(VENV)/bin/ruff

.PHONY: setup test eval run lint clean

setup: ## Create the virtualenv, install the package, download Chinook
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	$(PY) scripts/download_data.py --dataset chinook

run: ## Start the MCP server over stdio
	$(VENV)/bin/safedb-mcp --config config.yaml

test: ## Run the test suite (everything except live_llm)
	$(PY) -m pytest -m "not live_llm"

eval: ## Replay the committed baseline eval run (available from P5)
	$(PY) -m eval.run_eval --split tune --config eval/configs/baseline.yaml --mode replay

lint: ## Ruff lint and format check
	$(RUFF) check .
	$(RUFF) format --check .

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
