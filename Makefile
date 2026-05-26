# md2pdf-weasy — package-level convenience targets
#
# Usage:
#   make test       # run the pytest suite (70-ish tests, ~2s)
#   make examples   # render every examples/**/*.md to PDF beside the source
#   make clean      # delete generated PDFs, .pytest_cache/, build artefacts

PY := python

.PHONY: test examples clean

test:
	$(PY) -m pytest

examples:
	$(PY) tools/render-examples.py

clean:
	rm -f examples/*/*.pdf
	rm -rf .pytest_cache/ build/ *.egg-info pdf/__pycache__ tests/__pycache__ tools/__pycache__
