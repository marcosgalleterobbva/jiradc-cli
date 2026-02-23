PYTHON ?= python3

.PHONY: clean build check publish-testpypi publish-pypi

clean:
	rm -rf build dist *.egg-info

build: clean
	$(PYTHON) -m build

check:
	$(PYTHON) -m twine check dist/*

publish-testpypi:
	$(PYTHON) -m twine upload --repository testpypi dist/*

publish-pypi:
	$(PYTHON) -m twine upload dist/*
