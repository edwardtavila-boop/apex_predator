.PHONY: test lint verify backtest-demo firm-gate preflight all clean

PY ?= python
SPEC ?= apex_predator/docs/firm_spec_crypto_perp.json

test:
	pytest tests/ -q

lint:
	ruff check apex_predator
	ruff format --check apex_predator

verify:
	$(PY) -m apex_predator.scripts.verify_all

backtest-demo:
	$(PY) -m apex_predator.scripts.run_backtest_demo

firm-gate:
	$(PY) -m apex_predator.scripts.engage_firm_board --spec $(SPEC)

preflight:
	$(PY) -m apex_predator.scripts.preflight

all: lint test verify

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache coverage.xml .coverage
