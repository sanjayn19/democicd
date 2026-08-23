.PHONY: validate test package

validate:
	python scripts/validate_dags.py dags
	python -m compileall -q dags scripts tests

test: validate
	python -m unittest discover -s tests

package:
	python scripts/build_bundle.py --environment local --source dags --output build
