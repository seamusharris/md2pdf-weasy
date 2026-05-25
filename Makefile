# md2pdf-weasy — package-level convenience targets
#
# Usage:
#   make test       # run the pytest suite (70-ish tests, ~2s)
#   make samples    # render tests/sample.md with each theme into samples/
#   make clean      # delete samples/, .pytest_cache/, build artefacts

PY := python

.PHONY: test samples clean

test:
	$(PY) -m pytest

samples:
	$(PY) tools/render-samples.py

clean:
	rm -rf samples/ .pytest_cache/ build/ *.egg-info pdf/__pycache__ tests/__pycache__ tools/__pycache__
