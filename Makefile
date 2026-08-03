# md2pdf-weasy — package-level convenience targets
#
# Usage:
#   make setup      # one-time: create .venv/ and install package + test deps
#   make test       # run the pytest suite (~80 tests, ~2s)
#   make examples   # render every examples/**/*.md to PDF beside the source
#   make distribution-preflight  # check an exact environment/recipient tuple
#   make clean      # delete generated PDFs, .pytest_cache/, build artefacts
#
# All targets use .venv/bin/python so you don't need to activate the venv.
# WeasyPrint additionally requires Pango at the system level
# (`brew install pango` on macOS).

PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: setup test examples distribution-preflight visual-acceptance visual-acceptance-prune compatibility-v0.1 compatibility-v0.1-verify compatibility-v0.1-concurrency compatibility-v0.1-prune clean

setup:
	python3 -m venv .venv
	$(PIP) install -e ".[test]"

test:
	$(PY) -m pytest

examples:
	$(PY) tools/render-examples.py

distribution-preflight:
	$(PY) tools/distribution_entitlement.py \
		--operation "$${MD2PDF_OPERATION:-}" \
		--environment "$${MD2PDF_ENVIRONMENT:-}" \
		--recipient "$${MD2PDF_RECIPIENT:-}"

visual-acceptance:
	$(PY) tools/visual_acceptance.py generate

visual-acceptance-prune:
	$(PY) tools/visual_acceptance.py prune --apply

compatibility-v0.1:
	$(PY) tools/compatibility_v010.py generate

compatibility-v0.1-verify:
	$(PY) tools/compatibility_v010.py verify $(CANDIDATE)

compatibility-v0.1-concurrency:
	MD2PDF_COMPAT_REAL=1 $(PY) -m pytest -q tests/test_compatibility.py -k two_real_generators

compatibility-v0.1-prune:
	$(PY) tools/compatibility_v010.py prune --apply

clean:
	rm -f examples/*/*.pdf
	rm -rf .pytest_cache/ build/ *.egg-info pdf/__pycache__ tests/__pycache__ tools/__pycache__
	$(PY) tools/visual_acceptance.py prune --apply
	$(PY) tools/compatibility_v010.py prune --apply
