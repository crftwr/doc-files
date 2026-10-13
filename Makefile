# Development tasks for doc-files. Run from the repo root.
#
#   make dev       set up .venv with the package, extras and build tools
#   make test      run the full test suite
#   make dump FILE=report.docx FORMAT=markdown
#                  print one document (text, markdown or json)
#   make dist      build the sdist and wheel into dist/
#
# `make help` lists every target.

VENV   := .venv
PYTHON ?= $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python3)

.DEFAULT_GOAL := help

.PHONY: help
help:  ## List the targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "} {printf "  %-12s %s\n", $$1, $$2}'

$(VENV)/bin/python:
	python3 -m venv $(VENV)

.PHONY: venv
venv: $(VENV)/bin/python  ## Create .venv if it is missing

.PHONY: dev
dev: venv  ## Install the package editable, with all extras and build tools
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/python -m pip install -e ".[pdf,test]" build twine

.PHONY: test
test:  ## Run the full test suite
	$(PYTHON) -m pytest test/ -v

.PHONY: test-core
test-core:  ## Run the tests on a bare install (no extras but pytest), in a temp venv
	rm -rf temp/venv-core
	python3 -m venv temp/venv-core
	temp/venv-core/bin/python -m pip install --quiet . pytest
	cd temp && venv-core/bin/python -m pytest ../test/ -v

FORMAT ?= text

.PHONY: dump
dump:  ## Print FILE as FORMAT (text, markdown or json)
	@test -n "$(FILE)" || { echo 'usage: make dump FILE=<document> [FORMAT=text|markdown|json]' >&2; exit 2; }
	$(PYTHON) -m doc_files dump -f $(FORMAT) "$(FILE)"

.PHONY: dist
dist: clean-dist  ## Build the sdist and wheel into dist/
	$(PYTHON) -m build

.PHONY: check
check: dist  ## Build, then check the distribution metadata
	$(PYTHON) -m twine check dist/*

.PHONY: upload
upload: check  ## Upload dist/ to PyPI
	$(PYTHON) -m twine upload dist/*

.PHONY: clean-dist
clean-dist:
	rm -rf dist build *.egg-info

.PHONY: clean
clean: clean-dist  ## Remove build output and caches
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache temp
