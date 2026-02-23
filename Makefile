PYTHON ?= python3

.PHONY: clean build check publish-testpypi publish-pypi bump-version bump-version-% bump-patch bump-minor bump-major

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

bump-version:
	@if [ -z "$(PART)" ]; then echo "Set PART=patch|minor|major"; exit 1; fi
	bump-my-version bump $(PART)

bump-version-%:
	bump-my-version bump $*

bump-patch: bump-version-patch

bump-minor: bump-version-minor

bump-major: bump-version-major
