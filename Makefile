# md2pdf-weasy — package-level convenience targets
#
# Usage:
#   make setup      # one-time: create .venv/ and install package + test deps
#   make test       # run the pytest suite (~80 tests, ~2s)
#   make examples   # render every examples/**/*.md to PDF beside the source
#   make clean      # delete generated PDFs, .pytest_cache/, build artefacts
#
# All targets use .venv/bin/python so you don't need to activate the venv.
# WeasyPrint additionally requires Pango at the system level
# (`brew install pango` on macOS).

PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: setup test examples visual-acceptance visual-acceptance-prune clean

setup:
	python3 -m venv .venv
	$(PIP) install -e ".[test]"

test:
	$(PY) -m pytest

examples:
	$(PY) tools/render-examples.py

visual-acceptance:
	$(PY) tools/visual_acceptance.py generate

visual-acceptance-prune:
	$(PY) tools/visual_acceptance.py prune --apply

clean:
	rm -f examples/*/*.pdf
	rm -rf .pytest_cache/ build/ *.egg-info pdf/__pycache__ tests/__pycache__ tools/__pycache__
	$(PY) tools/visual_acceptance.py prune --apply
