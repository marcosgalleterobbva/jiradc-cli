# jiradc-cli

Typer CLI for Jira Data Center that authenticates with a browser session cookie (no PAT required).

Agent-oriented project docs:
- `AGENTS.md`
- `docs/PROJECT_OVERVIEW.md`
- `docs/COMMAND_REFERENCE.md`
- `docs/DEVELOPMENT_NOTES.md`

The endpoint set was selected from the OpenAPI/Postman files in `resources/` for common end-user workflows:
- Authentication/session validation (`/rest/auth/1/session`)
- User identity (`/rest/api/2/myself`)
- Project discovery (`/rest/api/2/project`)
- Issue search/read/create (`/rest/api/2/search`, `/rest/api/2/issue`, `/rest/api/2/issue/{issueIdOrKey}`)
- Comments (`/rest/api/2/issue/{issueIdOrKey}/comment`)
- Workflow transitions (`/rest/api/2/issue/{issueIdOrKey}/transitions`)
- Assignment (`/rest/api/2/issue/{issueIdOrKey}/assignee`)

## Install

```bash
pip install -e .
```

## Login with Browser Cookie

Export the cookie from an already logged-in Jira browser session, then run:

```bash
jiradc login --base-url https://jira.example.com
```

The command then pauses and asks you to copy your Jira `Cookie` header value to clipboard, reads it from clipboard, and validates it against `/rest/auth/1/session`.
On macOS this uses `pbpaste`.
During login, the CLI automatically reduces large browser cookie sets to Jira-relevant session cookies first (for better compatibility with SSO/WAF setups), and falls back to the full cookie if needed.

You can also pass it directly:

```bash
jiradc login --base-url https://jira.example.com --cookie "JSESSIONID=...; atlassian.xsrf.token=..."
```

Config is saved in:
- `~/.config/jiradc-cli/config.json`

## Commands

```bash
jiradc whoami
jiradc project list
jiradc issue search --jql "assignee = currentUser() AND statusCategory != Done"
jiradc issue get PROJ-123
jiradc issue create --project PROJ --summary "New task" --issue-type Task --description "Created from CLI"
jiradc issue comments PROJ-123
jiradc issue comment-add PROJ-123 --body "Working on this now."
jiradc issue transitions PROJ-123
jiradc issue transition PROJ-123 --id 31 --comment "Moving to In Progress"
jiradc issue assign PROJ-123 --username alice
jiradc logout
```
