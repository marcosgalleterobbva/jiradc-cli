# Publishing to PyPI

This project uses `setuptools` + `build` for artifacts and `twine` for uploads.

## 1. One-time setup

Create PyPI API tokens:

- TestPyPI token from [https://test.pypi.org/manage/account/token/](https://test.pypi.org/manage/account/token/)
- PyPI token from [https://pypi.org/manage/account/token/](https://pypi.org/manage/account/token/)

Export credentials before uploading:

```bash
export TWINE_USERNAME="__token__"
export TWINE_PASSWORD="pypi-<your-token>"
```

For TestPyPI, use the TestPyPI token value in `TWINE_PASSWORD`.

## 2. Install release tooling

```bash
pip install -e ".[release]"
```

## 3. Build distribution artifacts

```bash
make bump-patch   # or make bump-minor / make bump-major
make build
```

Artifacts are created under `dist/`:

- source distribution (`.tar.gz`)
- wheel (`.whl`)

## 4. Validate package metadata

```bash
make check
```

## 5. Publish to TestPyPI (recommended first)

```bash
make publish-testpypi
```

## 6. Publish to PyPI

```bash
make publish-pypi
```

## 7. Verify install

```bash
pip install jiradc-cli
jiradc --help
```

## Release checklist

1. Bump version with `make bump-patch` (or `make bump-minor` / `make bump-major`).
2. Rebuild with `make build`.
3. Run `make check`.
4. Upload to TestPyPI and verify install.
5. Upload to PyPI.
6. Tag release in GitHub.
