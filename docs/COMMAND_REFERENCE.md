# Command Reference

## Conventions

- Base URL and cookie are persisted after login.
- All API paths below are relative to `/rest`.
- Commands favor concise human output; most include `--raw` for full JSON.
- Mutating commands (`POST/PUT/PATCH/DELETE`) send `X-Atlassian-Token: no-check` to satisfy Jira XSRF checks.

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

### `jiradc project components <PROJECT_ID_OR_KEY>`

- Endpoint: `GET /api/2/project/{projectIdOrKey}/components`
- Output: component id, name, lead
- Option: `--raw`

### `jiradc project versions <PROJECT_ID_OR_KEY>`

- Endpoint: `GET /api/2/project/{projectIdOrKey}/versions`
- Options:
  - `--expand`
  - `--raw`

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
  - `--custom-field FIELD_ID=VALUE` (repeatable; `VALUE` can be JSON)
  - `--fields-json <JSON_OR_@FILE>` (merged into `fields`; can override defaults)
  - `--raw`

### `jiradc issue createmeta-types`

- Primary endpoint: `GET /api/2/issue/createmeta/{projectIdOrKey}/issuetypes`
- Fallback endpoint: `GET /api/2/issue/createmeta?projectKeys=<KEY>&expand=projects.issuetypes`
- Required:
  - `--project`
- Optional:
  - `--max-results` (default `50`)
  - `--start-at` (default `0`)
  - `--raw`

### `jiradc issue createmeta-fields`

- Primary endpoint: `GET /api/2/issue/createmeta/{projectIdOrKey}/issuetypes/{issueTypeId}`
- Fallback endpoint: `GET /api/2/issue/createmeta?projectKeys=<KEY>&issuetypeIds=<ID>&expand=projects.issuetypes.fields`
- Required:
  - `--project`
  - `--issue-type-id`
- Optional:
  - `--max-results` (default `200`)
  - `--start-at` (default `0`)
  - `--raw`

### `jiradc issue editmeta <ISSUE_KEY>`

- Endpoint: `GET /api/2/issue/{issueIdOrKey}/editmeta`
- Optional:
  - `--raw`

### `jiradc issue edit <ISSUE_KEY>`

- Endpoint: `PUT /api/2/issue/{issueIdOrKey}`
- Supports field updates:
  - `--summary`
  - `--description`
  - `--priority`
  - `--assignee`
  - `--clear-assignee`
  - `--labels`
- Optional:
  - `--notify-users / --no-notify-users`

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

### `jiradc issue comment-get <ISSUE_KEY> <COMMENT_ID>`

- Endpoint: `GET /api/2/issue/{issueIdOrKey}/comment/{id}`
- Optional:
  - `--expand`
  - `--raw`

### `jiradc issue comment-update <ISSUE_KEY> <COMMENT_ID>`

- Endpoint: `PUT /api/2/issue/{issueIdOrKey}/comment/{id}`
- Required:
  - `--body`
- Optional:
  - `--expand`
  - `--raw`

### `jiradc issue comment-delete <ISSUE_KEY> <COMMENT_ID>`

- Endpoint: `DELETE /api/2/issue/{issueIdOrKey}/comment/{id}`

### `jiradc issue attachment-add <ISSUE_KEY>`

- Endpoint: `POST /api/2/issue/{issueIdOrKey}/attachments`
- Required:
  - `--file` (repeatable)
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
  - `--username`

### `jiradc issue watchers <ISSUE_KEY>`

- Endpoint: `GET /api/2/issue/{issueIdOrKey}/watchers`
- Optional:
  - `--raw`

### `jiradc issue watcher-add <ISSUE_KEY>`

- Endpoint: `POST /api/2/issue/{issueIdOrKey}/watchers`
- Optional:
  - `--username` (if omitted, adds current user)

### `jiradc issue watcher-remove <ISSUE_KEY>`

- Endpoint: `DELETE /api/2/issue/{issueIdOrKey}/watchers`
- Required:
  - `--username`

### `jiradc issue votes <ISSUE_KEY>`

- Endpoint: `GET /api/2/issue/{issueIdOrKey}/votes`
- Optional:
  - `--raw`

### `jiradc issue vote-add <ISSUE_KEY>`

- Endpoint: `POST /api/2/issue/{issueIdOrKey}/votes`
- Optional:
  - `--raw`

### `jiradc issue vote-remove <ISSUE_KEY>`

- Endpoint: `DELETE /api/2/issue/{issueIdOrKey}/votes`

### `jiradc issue worklogs <ISSUE_KEY>`

- Endpoint: `GET /api/2/issue/{issueIdOrKey}/worklog`
- Optional:
  - `--raw`

### `jiradc issue worklog-get <ISSUE_KEY> <WORKLOG_ID>`

- Endpoint: `GET /api/2/issue/{issueIdOrKey}/worklog/{id}`
- Optional:
  - `--raw`

### `jiradc issue worklog-add <ISSUE_KEY>`

- Endpoint: `POST /api/2/issue/{issueIdOrKey}/worklog`
- Required:
  - `--time-spent`
- Optional:
  - `--comment`
  - `--started`
  - `--adjust-estimate` (`new|leave|manual|auto`)
  - `--new-estimate` (required when adjust is `new`)
  - `--reduce-by` (required when adjust is `manual`)
  - `--raw`

### `jiradc issue worklog-update <ISSUE_KEY> <WORKLOG_ID>`

- Endpoint: `PUT /api/2/issue/{issueIdOrKey}/worklog/{id}`
- Update fields:
  - `--time-spent`
  - `--comment`
  - `--started`
- Optional:
  - `--adjust-estimate` (`new|leave|auto`)
  - `--new-estimate` (required when adjust is `new`)
  - `--raw`

### `jiradc issue worklog-delete <ISSUE_KEY> <WORKLOG_ID>`

- Endpoint: `DELETE /api/2/issue/{issueIdOrKey}/worklog/{id}`
- Optional:
  - `--adjust-estimate` (`new|leave|manual|auto`)
  - `--new-estimate` (required when adjust is `new`)
  - `--increase-by` (required when adjust is `manual`)

### `jiradc issue picker`

- Endpoint: `GET /api/2/issue/picker`
- Required:
  - `--query`
- Optional:
  - `--current-project-id`
  - `--current-issue-key`
  - `--current-jql`
  - `--show-subtasks / --no-show-subtasks`
  - `--show-subtask-parent / --no-show-subtask-parent`
  - `--raw`

### `jiradc issue link-types`

- Endpoint: `GET /api/2/issueLinkType`
- Optional:
  - `--raw`

### `jiradc issue link-create`

- Endpoint: `POST /api/2/issueLink`
- Required:
  - `--type`
  - `--inward-issue`
  - `--outward-issue`
- Optional:
  - `--comment`

## Filter commands

### `jiradc filter favourites`

- Endpoint: `GET /api/2/filter/favourite`
- Optional:
  - `--expand`
  - `--raw`

### `jiradc filter get <FILTER_ID>`

- Endpoint: `GET /api/2/filter/{id}`
- Optional:
  - `--expand`
  - `--raw`

### `jiradc filter create`

- Endpoint: `POST /api/2/filter`
- Required:
  - `--name`
  - `--jql`
- Optional:
  - `--description`
  - `--favourite / --no-favourite`
  - `--raw`

### `jiradc filter update <FILTER_ID>`

- Endpoint: `PUT /api/2/filter/{id}`
- Update fields:
  - `--name`
  - `--jql`
  - `--description`
- Optional:
  - `--raw`

## JQL commands

### `jiradc jql suggest`

- Endpoint: `GET /api/2/jql/autocompletedata/suggestions`
- Optional:
  - `--field-name`
  - `--field-value`
  - `--predicate-name`
  - `--predicate-value`
  - `--raw`

## Agile commands

### `jiradc agile board list`

- Endpoint: `GET /agile/1.0/board`
- Optional:
  - `--max-results` (default `50`)
  - `--start-at` (default `0`)
  - `--name`
  - `--project`
  - `--type` (comma-separated)
  - `--raw`

### `jiradc agile board backlog <BOARD_ID>`

- Endpoint: `GET /agile/1.0/board/{boardId}/backlog`
- Optional:
  - `--jql`
  - `--fields` (default `summary,status,assignee`)
  - `--max-results` (default `50`)
  - `--start-at` (default `0`)
  - `--validate-query / --no-validate-query`
  - `--expand`
  - `--raw`

### `jiradc agile board sprints <BOARD_ID>`

- Endpoint: `GET /agile/1.0/board/{boardId}/sprint`
- Optional:
  - `--state` (comma-separated)
  - `--max-results` (default `50`)
  - `--start-at` (default `0`)
  - `--raw`

### `jiradc agile sprint issues <SPRINT_ID>`

- Endpoint: `GET /agile/1.0/sprint/{sprintId}/issue`
- Optional:
  - `--jql`
  - `--fields` (default `summary,status,assignee`)
  - `--max-results` (default `50`)
  - `--start-at` (default `0`)
  - `--validate-query / --no-validate-query`
  - `--expand`
  - `--raw`

### `jiradc agile sprint move-issues <SPRINT_ID>`

- Endpoint: `POST /agile/1.0/sprint/{sprintId}/issue`
- Required:
  - `--issue` (repeatable, max 50)

### `jiradc agile issue rank`

- Endpoint: `PUT /agile/1.0/issue/rank`
- Required:
  - `--issue` (repeatable, max 50)
  - exactly one of `--before` or `--after`
- Optional:
  - `--rank-custom-field-id`
  - `--raw`

### `jiradc agile issue estimation <ISSUE_KEY>`

- Endpoint: `GET /agile/1.0/issue/{issueIdOrKey}/estimation`
- Required:
  - `--board-id`
- Optional:
  - `--raw`

### `jiradc agile issue estimation-set <ISSUE_KEY>`

- Endpoint: `PUT /agile/1.0/issue/{issueIdOrKey}/estimation`
- Required:
  - `--board-id`
  - `--value`
- Optional:
  - `--raw`

## Recommended JQL presets

- My open issues:
  - `assignee = currentUser() AND resolution = Unresolved ORDER BY updated DESC`
- My in-progress work:
  - `assignee = currentUser() AND statusCategory = "In Progress" ORDER BY updated DESC`
- Project backlog subset:
  - `project = PROJ AND statusCategory != Done ORDER BY priority DESC, updated DESC`
