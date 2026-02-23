# Project Overview

## What this CLI does

`jiradc` is a Jira Data Center command-line client optimized for user workflows:

- inspect identity and projects
- search, inspect, create, and edit issues
- read/add/update/delete comments
- upload attachments
- manage watchers and votes
- add/update/delete worklogs
- transition workflow status and assign issues
- manage personal filters and JQL suggestions
- run Agile board/sprint operations (list/backlog/sprints/rank/estimation)

It is intentionally centered on authenticated user actions rather than admin-level configuration.

## Why cookie-based auth

This environment uses SSO and does not allow PATs. The CLI therefore uses an exported browser `Cookie` header from an already logged-in Jira session.

Key implications:

- login is a local setup action (`jiradc login`)
- session validity depends on browser-side SSO/session lifetime
- stale cookies are the primary auth failure mode

## Core architecture

1. CLI layer (`jiradc_cli/main.py`)
   - Typer commands
   - input validation and display formatting
   - login flow and session verification

2. Config layer (`jiradc_cli/config.py`)
   - store/load config from `~/.config/jiradc-cli/config.json`
   - normalize base URL and cookie
   - minimize large cookie sets to Jira-relevant keys

3. API layer (`jiradc_cli/client.py`)
   - single request entry point for all Jira calls
   - default headers (Accept, Cookie, X-Requested-With, User-Agent)
   - mutating requests automatically include `X-Atlassian-Token: no-check`
   - transport and HTTP error normalization

## Data flow for a typical command

1. Command executes in `main.py`.
2. `_require_client()` loads config.
3. Command calls `JiraClient.request(...)`.
4. Client sends request to `{base_url}/rest{path}`.
5. Response is normalized:
   - JSON returned as Python objects
   - 204/empty returns `None`
   - failures mapped to `JiraApiError`/`JiraTransportError`
6. Command prints readable summary or `--raw` JSON.

## Login/verification flow

1. Gather `base_url`.
2. Resolve cookie:
   - `--cookie`, or
   - clipboard read with retry guard for accidental URL clipboard content.
3. Normalize config values.
4. Verify with candidate cookie variants:
   - minimized Jira-focused cookie set first
   - full cookie fallback
   - endpoint order: `/api/2/myself` then `/auth/1/session`
5. Save final cookie used to `~/.config/jiradc-cli/config.json`.

## Known constraints

- No retry/backoff logic yet.
- No pagination helper abstraction yet (commands pass paging params directly).
- No centralized schema models (uses dict-based payload handling).
- No automated tests yet.

## Extension strategy

For new commands:

1. Confirm endpoint in OpenAPI/Postman under `resources/`.
2. Add Typer command in `main.py` under the appropriate group.
3. Use `_require_success` wrapper and `JiraClient.request`.
4. Provide concise default output and optional `--raw` mode.
5. Update `README.md` and `docs/COMMAND_REFERENCE.md`.
