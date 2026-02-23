# AGENTS.md

This repository contains a Typer CLI (`jiradc`) for Jira Data Center focused on end-user workflows using browser session cookies (SSO-compatible, no PAT requirement).

## Project intent

- Problem: Users authenticate to Jira Data Center via SSO and cannot use PATs.
- Solution: Accept browser-exported cookies and call Jira REST endpoints for day-to-day issue workflows.
- Audience: End users (issue triage and updates), not Jira administrators.

## Tech stack

- Python `>=3.10`
- CLI framework: `typer`
- HTTP client: `requests`
- Packaging: `setuptools` (via `pyproject.toml`)

## Repository map

- `pyproject.toml`: package metadata, dependencies, CLI entry point (`jiradc = jiradc_cli.main:main`)
- `jiradc_cli/main.py`: CLI commands and auth/login flow
- `jiradc_cli/client.py`: Jira HTTP client + error normalization
- `jiradc_cli/config.py`: local config and cookie parsing/minimization
- `resources/jira_software_dc_10000_swagger.v3.txt`: OpenAPI source (single-line JSON)
- `resources/jira.10000.postman.txt`: Postman collection source
- `README.md`: user-facing quickstart
- `docs/PUBLISHING.md`: PyPI/TestPyPI release workflow via `build` + `twine`
- `Makefile`: release commands (`build`, `check`, `publish-testpypi`, `publish-pypi`)

## Authentication model

- Credentials are stored at `~/.config/jiradc-cli/config.json` with keys:
  - `base_url`
  - `cookie`
- `jiradc login` supports:
  - clipboard cookie acquisition (default)
  - explicit `--cookie`
  - optional verification skip (`--skip-verify`)
- Verification strategy:
  1. try `GET /rest/api/2/myself`
  2. fallback `GET /rest/auth/1/session`
- Cookie minimization is applied during verification first (Jira/session cookies only), then full-cookie fallback.

## Implemented command groups

- root:
  - `login`
  - `logout`
  - `whoami`
- `project`:
  - `list`
- `issue`:
  - `get`
  - `search`
  - `create`
  - `comments`
  - `comment-add`
  - `transitions`
  - `transition`
  - `assign`

See `docs/COMMAND_REFERENCE.md` for details.

## Non-goals (current state)

- No admin/configuration workflows (permission schemes, project creation/update, workflow schemes, etc.).
- No PAT/basic-auth flow.
- No unit/integration test suite in-repo yet.

## How to run locally

```bash
pip install -e .
jiradc --help
```

## Build and publish

```bash
pip install -e ".[release]"
make build
make check
make publish-testpypi
make publish-pypi
```

## Conventions for future agents

- Keep end-user workflow commands first; avoid adding admin-only APIs unless explicitly requested.
- Reuse `JiraClient` for HTTP calls; keep endpoint paths as `/api/2/...` or `/auth/1/...` (client prefixes `/rest`).
- For new commands, maintain both:
  - human-readable default output
  - `--raw` JSON output (when practical)
- Preserve clear errors through `_require_success` and `JiraApiError`/`JiraTransportError`.
- Treat cookies as secrets; never print full cookie values in output or logs.

## Suggested next features

- `issue mine` shortcut (`assignee = currentUser()` JQL preset)
- `issue edit` (summary/description/priority fields)
- `issue worklog` add/list
- `project recent` using `GET /api/2/project?recent=<N>`
