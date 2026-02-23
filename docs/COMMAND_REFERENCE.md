# Command Reference

## Conventions

- Base URL is persisted after login.
- All API paths below are relative to `/rest`.
- Commands favor concise human output; many include `--raw` for full JSON.

## Root commands

### `jiradc login`

- Purpose: store Jira URL + cookie and verify session.
- Cookie input:
  - clipboard by default
  - or `--cookie`
- Verification endpoints:
  - `GET /api/2/myself`
  - fallback `GET /auth/1/session`
- Options:
  - `--base-url`
  - `--cookie`
  - `--cookie-from-clipboard / --no-cookie-from-clipboard`
  - `--skip-verify`

### `jiradc logout`

- Purpose: delete local config file.
- API calls: none

### `jiradc whoami`

- Endpoint: `GET /api/2/myself`
- Output: display name, username, email, active status
- Option: `--raw`

## Project commands

### `jiradc project list`

- Endpoint: `GET /api/2/project`
- Output: `KEY NAME [projectTypeKey]`
- Option: `--raw`

## Issue commands

### `jiradc issue search`

- Endpoint: `GET /api/2/search`
- Required:
  - `--jql`
- Optional:
  - `--max-results` (default `20`)
  - `--start-at` (default `0`)
  - `--fields` (default `summary,status,assignee`)
  - `--raw`

### `jiradc issue get <ISSUE_KEY>`

- Endpoint: `GET /api/2/issue/{issueIdOrKey}`
- Optional:
  - `--expand`
  - `--raw`

### `jiradc issue create`

- Endpoint: `POST /api/2/issue`
- Required:
  - `--project`
  - `--summary`
- Optional:
  - `--issue-type` (default `Task`)
  - `--description`
  - `--assignee`
  - `--raw`

### `jiradc issue comments <ISSUE_KEY>`

- Endpoint: `GET /api/2/issue/{issueIdOrKey}/comment`
- Optional:
  - `--raw`

### `jiradc issue comment-add <ISSUE_KEY>`

- Endpoint: `POST /api/2/issue/{issueIdOrKey}/comment`
- Required:
  - `--body` (or prompt)
- Optional:
  - `--raw`

### `jiradc issue transitions <ISSUE_KEY>`

- Endpoint: `GET /api/2/issue/{issueIdOrKey}/transitions`
- Optional:
  - `--raw`

### `jiradc issue transition <ISSUE_KEY>`

- Endpoint: `POST /api/2/issue/{issueIdOrKey}/transitions`
- Required:
  - `--id` (transition ID)
- Optional:
  - `--comment`

### `jiradc issue assign <ISSUE_KEY>`

- Endpoint: `PUT /api/2/issue/{issueIdOrKey}/assignee`
- Required:
  - `--username` (or prompt)

## Recommended user-focused JQL presets

- My open issues:
  - `assignee = currentUser() AND resolution = Unresolved ORDER BY updated DESC`
- My in-progress work:
  - `assignee = currentUser() AND statusCategory = "In Progress" ORDER BY updated DESC`
- Project backlog subset:
  - `project = PROJ AND statusCategory != Done ORDER BY priority DESC, updated DESC`
