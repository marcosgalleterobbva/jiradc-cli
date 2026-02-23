# jiradc-cli

Typer CLI for Jira Data Center that authenticates with a browser session cookie (no PAT required).

Agent-oriented project docs:
- `AGENTS.md`
- `docs/PROJECT_OVERVIEW.md`
- `docs/COMMAND_REFERENCE.md`
- `docs/DEVELOPMENT_NOTES.md`
- `docs/PUBLISHING.md`

The endpoint set is selected from the OpenAPI/Postman files in `resources/` for common end-user workflows:
- Authentication/session validation (`/rest/auth/1/session`, `/rest/api/2/myself`)
- Project discovery (`/rest/api/2/project`, `/rest/api/2/project/{projectIdOrKey}/components`, `/rest/api/2/project/{projectIdOrKey}/versions`)
- Issue search/read/create/edit (`/rest/api/2/search`, `/rest/api/2/issue`, `/rest/api/2/issue/{issueIdOrKey}`, `/rest/api/2/issue/{issueIdOrKey}/editmeta`)
- Comments (`/rest/api/2/issue/{issueIdOrKey}/comment`, `/rest/api/2/issue/{issueIdOrKey}/comment/{id}`)
- Attachments (`/rest/api/2/issue/{issueIdOrKey}/attachments`)
- Watchers/votes/worklogs (`/rest/api/2/issue/{issueIdOrKey}/watchers`, `/rest/api/2/issue/{issueIdOrKey}/votes`, `/rest/api/2/issue/{issueIdOrKey}/worklog`)
- Transitions/assignment (`/rest/api/2/issue/{issueIdOrKey}/transitions`, `/rest/api/2/issue/{issueIdOrKey}/assignee`)
- Issue linking (`/rest/api/2/issueLink`, `/rest/api/2/issueLinkType`)
- Filter and JQL helpers (`/rest/api/2/filter`, `/rest/api/2/filter/favourite`, `/rest/api/2/jql/autocompletedata/suggestions`, `/rest/api/2/issue/picker`)
- Agile workflows (`/rest/agile/1.0/board`, `/rest/agile/1.0/sprint`, `/rest/agile/1.0/issue/rank`, `/rest/agile/1.0/issue/{issueIdOrKey}/estimation`)

## Install

```bash
pip install -e .
```

## Login with Browser Cookie

Export the cookie from an already logged-in Jira browser session, then run:

```bash
jiradc login --base-url https://jira.example.com
```

The command then pauses and asks you to copy your Jira `Cookie` header value to clipboard, reads it from clipboard, and validates it.
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
# Identity and projects
jiradc whoami
jiradc project list
jiradc project components PROJ
jiradc project versions PROJ

# Issues
jiradc issue search --jql "assignee = currentUser() AND statusCategory != Done"
jiradc issue get PROJ-123
jiradc issue create --project PROJ --summary "New task" --issue-type Task
jiradc issue editmeta PROJ-123
jiradc issue edit PROJ-123 --summary "Updated summary" --priority High

# Comments and attachments
jiradc issue comments PROJ-123
jiradc issue comment-add PROJ-123 --body "Working on this now."
jiradc issue comment-update PROJ-123 10100 --body "Latest update"
jiradc issue attachment-add PROJ-123 --file /tmp/screenshot.png

# Workflow and people
jiradc issue transitions PROJ-123
jiradc issue transition PROJ-123 --id 31 --comment "Moving to In Progress"
jiradc issue assign PROJ-123 --username alice
jiradc issue watchers PROJ-123
jiradc issue watcher-add PROJ-123 --username bob
jiradc issue votes PROJ-123
jiradc issue vote-add PROJ-123

# Worklogs
jiradc issue worklogs PROJ-123
jiradc issue worklog-add PROJ-123 --time-spent "1h 30m" --comment "Investigation"

# Linking and metadata
jiradc issue link-types
jiradc issue link-create --type Blocks --inward-issue PROJ-123 --outward-issue PROJ-456
jiradc issue createmeta-types --project PROJ
jiradc issue createmeta-fields --project PROJ --issue-type-id 10001

# Filters and query assistance
jiradc filter favourites
jiradc filter create --name "My Open" --jql "assignee = currentUser() AND resolution = Unresolved"
jiradc jql suggest --field-name status --field-value "In"
jiradc issue picker --query "PROJ-"

# Agile
jiradc agile board list
jiradc agile board backlog 12
jiradc agile board sprints 12 --state active,future
jiradc agile sprint issues 55
jiradc agile issue rank --issue PROJ-123 --issue PROJ-124 --before PROJ-122
jiradc agile issue estimation PROJ-123 --board-id 12
jiradc agile issue estimation-set PROJ-123 --board-id 12 --value 8

jiradc logout
```

## Build and publish

Project metadata includes GitHub links in `pyproject.toml`:
- Homepage: `https://github.com/marcosgalleterobbva/jiradc-cli`
- Repository: `https://github.com/marcosgalleterobbva/jiradc-cli`
- Issues: `https://github.com/marcosgalleterobbva/jiradc-cli/issues`

Release tooling:

```bash
pip install -e ".[release]"
make bump-patch   # or: make bump-minor / make bump-major
make build
make check
make publish-testpypi
make publish-pypi
```

See `docs/PUBLISHING.md` for the full release workflow.
