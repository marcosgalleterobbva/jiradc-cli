# Development Notes

## Setup

```bash
pip install -e .
python3 -m compileall jiradc_cli
```

## Entry points

- package script: `jiradc` (configured in `pyproject.toml`)
- module execution: `python3 -m jiradc_cli`

## Error model

- `JiraTransportError`: request/network failures
- `JiraApiError`: HTTP error responses (status >= 400)
- `ConfigError`: invalid/missing local configuration

Command handlers should route failures through `_require_success(...)` so users get clear CLI errors.

## Safe extension checklist

When adding a new command:

1. Confirm endpoint/method in `resources/jira_software_dc_10000_swagger.v3.txt`.
2. Implement command in `jiradc_cli/main.py` within existing or new Typer subgroup.
3. Build request via `JiraClient.request(...)`.
4. Provide:
   - readable default output
   - `--raw` JSON output if the response is non-trivial
5. Add usage snippet to `README.md`.
6. Add endpoint mapping to `docs/COMMAND_REFERENCE.md`.
7. Run `python3 -m compileall jiradc_cli`.

## Cookie handling notes

- The CLI stores cookie strings locally in plain JSON config.
- File permissions are constrained where possible:
  - config directory: `0700`
  - config file: `0600`
- Never print full cookie contents in logs or command output.

## Known gaps / technical debt

- No automated tests.
- No typed response models.
- No endpoint-specific retry behavior.
- No command for "my issues" shortcut yet (currently done via `issue search --jql ...`).

## Candidate roadmap (user workflow focus)

- `issue mine` command with optional state filters.
- `issue edit` for summary/description/priority.
- `issue worklog add/list`.
- `project recent` wrapper for `GET /api/2/project?recent=...`.
