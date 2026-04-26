.PHONY: pkg-link test lint verify backtest-demo firm-gate preflight all clean

# The repo is laid out flat (package dir IS the repo root). Make
# imports work by symlinking the repo into a parent dir named
# apex_predator and putting that parent on PYTHONPATH. This matches
# ci.yml's "wire apex_predator as importable package" step.
PKG_ROOT ?= /tmp/_pkg_root
PY ?= python
SPEC ?= docs/firm_spec_crypto_perp.json

# Compose the env-prefix every target uses. Targets that run python
# code prepend $(WITH_ENV) to ensure the symlink + PYTHONPATH are set.
WITH_ENV = PYTHONPATH=$(PKG_ROOT):$(CURDIR) PYTHONDONTWRITEBYTECODE=1

pkg-link:
	@mkdir -p $(PKG_ROOT)
	@if [ ! -L $(PKG_ROOT)/apex_predator ]; then \
	    ln -sf $(CURDIR) $(PKG_ROOT)/apex_predator ; \
	fi

test: pkg-link
	$(WITH_ENV) pytest tests/ -q -m "not slow"

# Lint scope mirrors .github/workflows/ci.yml -- production code only.
lint:
	ruff check \
	    strategies/ \
	    scripts/_bump_roadmap_v0_1_4*.py \
	    scripts/_pre_commit_check.py \
	    scripts/_new_roadmap_bump.py

verify: pkg-link
	$(WITH_ENV) $(PY) -m apex_predator.scripts.verify_all

backtest-demo: pkg-link
	$(WITH_ENV) $(PY) -m apex_predator.scripts.run_backtest_demo

firm-gate: pkg-link
	$(WITH_ENV) $(PY) -m apex_predator.scripts.engage_firm_board --spec $(SPEC)

preflight: pkg-link
	$(WITH_ENV) $(PY) -m apex_predator.scripts.preflight

all: lint test verify

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache coverage.xml .coverage
