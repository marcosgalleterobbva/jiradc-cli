from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import typer

from .client import JiraApiError, JiraClient, JiraTransportError
from .config import (
    ConfigError,
    JiraConfig,
    clear_config,
    cookie_variants_for_auth,
    load_config,
    normalize_base_url,
    normalize_cookie,
    save_config,
)

app = typer.Typer(help="CLI for Jira Data Center using browser session cookies.")
project_app = typer.Typer(help="Project-related operations.")
issue_app = typer.Typer(help="Issue-related operations.")
filter_app = typer.Typer(help="Filter-related operations.")
jql_app = typer.Typer(help="JQL helper operations.")
agile_app = typer.Typer(help="Agile board/sprint operations.")
board_app = typer.Typer(help="Agile board operations.")
sprint_app = typer.Typer(help="Agile sprint operations.")
agile_issue_app = typer.Typer(help="Agile issue operations.")

app.add_typer(project_app, name="project")
app.add_typer(issue_app, name="issue")
app.add_typer(filter_app, name="filter")
app.add_typer(jql_app, name="jql")
app.add_typer(agile_app, name="agile")
agile_app.add_typer(board_app, name="board")
agile_app.add_typer(sprint_app, name="sprint")
agile_app.add_typer(agile_issue_app, name="issue")


def _echo_json(payload: Any) -> None:
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))


def _require_client() -> JiraClient:
    try:
        config = load_config()
    except ConfigError as exc:
        raise typer.Exit(code=_fail(f"{exc}. Run 'jiradc login' first."))
    return JiraClient(config)


def _fail(message: str) -> int:
    typer.secho(message, fg=typer.colors.RED, err=True)
    return 1


def _require_success(label: str, action: Callable[[], Any]) -> Any:
    try:
        return action()
    except (ConfigError, JiraApiError, JiraTransportError) as exc:
        raise typer.Exit(code=_fail(f"{label} failed: {exc}"))


def _read_clipboard() -> str:
    candidates: list[list[str]] = []
    if sys.platform == "darwin" and shutil.which("pbpaste"):
        candidates.append(["pbpaste"])
    elif sys.platform.startswith("win"):
        candidates.append(["powershell", "-NoProfile", "-Command", "Get-Clipboard"])
    else:
        if shutil.which("wl-paste"):
            candidates.append(["wl-paste", "--no-newline"])
        if shutil.which("xclip"):
            candidates.append(["xclip", "-selection", "clipboard", "-o"])
        if shutil.which("xsel"):
            candidates.append(["xsel", "--clipboard", "--output"])

    last_error = "No clipboard utility found."
    for cmd in candidates:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            value = result.stdout.strip()
            if value:
                return value
            last_error = "Clipboard is empty."
        except Exception as exc:  # pragma: no cover
            last_error = str(exc)
    raise ConfigError(f"Unable to read cookie from clipboard. {last_error}")


def _looks_like_url(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _extract_username(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    name = payload.get("name")
    if isinstance(name, str) and name:
        return name
    display_name = payload.get("displayName")
    if isinstance(display_name, str) and display_name:
        return display_name
    session = payload.get("session")
    if isinstance(session, dict):
        session_name = session.get("name")
        if isinstance(session_name, str) and session_name:
            return session_name
    return None


def _verify_cookie_session(config: JiraConfig) -> tuple[JiraConfig, str]:
    errors: list[str] = []
    endpoints = ["/api/2/myself", "/auth/1/session"]

    for candidate_cookie in cookie_variants_for_auth(config.cookie):
        candidate = JiraConfig(base_url=config.base_url, cookie=candidate_cookie)
        client = JiraClient(candidate)
        for endpoint in endpoints:
            try:
                payload = client.request("GET", endpoint)
            except (JiraApiError, JiraTransportError) as exc:
                errors.append(f"{endpoint}: {exc}")
                continue

            username = _extract_username(payload)
            return JiraConfig(base_url=config.base_url, cookie=candidate_cookie), (username or "unknown")

    joined_errors = " | ".join(errors)
    raise ConfigError(
        "Cookie verification failed on Jira endpoints. "
        "Try copying only Jira session cookies (JSESSIONID, atlassian.xsrf.token, AWSALB/AWSALBCORS). "
        f"Details: {joined_errors}"
    )


def _split_csv(raw_value: str | None) -> list[str] | None:
    if raw_value is None:
        return None
    values = [item.strip() for item in raw_value.split(",") if item.strip()]
    return values or None


def _extract_issue_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("issues", "values"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [item for item in rows if isinstance(item, dict)]
    return []


def _print_issue_rows(rows: list[dict[str, Any]]) -> None:
    for issue in rows:
        issue_key = issue.get("key")
        issue_fields = issue.get("fields", {})
        if not isinstance(issue_fields, dict):
            issue_fields = {}
        summary = issue_fields.get("summary")
        status_name = None
        status = issue_fields.get("status")
        if isinstance(status, dict):
            status_name = status.get("name")
        assignee_name = None
        assignee = issue_fields.get("assignee")
        if isinstance(assignee, dict):
            assignee_name = assignee.get("displayName") or assignee.get("name")
        typer.echo(f"{str(issue_key):12} {status_name or '-':14} {assignee_name or '-':20} {summary}")


def _load_json_object_option(raw_value: str, option_name: str) -> dict[str, Any]:
    source = raw_value
    if raw_value.startswith("@"):
        path = Path(raw_value[1:]).expanduser()
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise typer.Exit(code=_fail(f"{option_name}: unable to read file {path}: {exc}"))

    try:
        payload = json.loads(source)
    except json.JSONDecodeError as exc:
        raise typer.Exit(code=_fail(f"{option_name}: invalid JSON ({exc.msg})."))

    if not isinstance(payload, dict):
        raise typer.Exit(code=_fail(f"{option_name}: expected a JSON object."))
    return payload


def _parse_custom_field_assignments(assignments: list[str]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for assignment in assignments:
        if "=" not in assignment:
            raise typer.Exit(
                code=_fail(
                    "--custom-field must use FIELD_ID=VALUE format "
                    "(VALUE can be plain text or JSON)."
                )
            )

        field_id, raw_value = assignment.split("=", 1)
        field_id = field_id.strip()
        value_text = raw_value.strip()

        if not field_id:
            raise typer.Exit(code=_fail("--custom-field must include a field id before '='."))
        if not value_text:
            raise typer.Exit(code=_fail(f"--custom-field {field_id}: value cannot be empty."))

        try:
            parsed_value = json.loads(value_text)
        except json.JSONDecodeError:
            parsed_value = value_text
        fields[field_id] = parsed_value
    return fields


def _collect_issue_create_extra_fields(
    custom_fields: list[str],
    fields_json: str | None,
) -> dict[str, Any]:
    merged = _parse_custom_field_assignments(custom_fields)
    if fields_json is not None:
        merged.update(_load_json_object_option(fields_json, "--fields-json"))
    return merged


def _extract_issue_types(payload: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return candidates

    direct = payload.get("issueTypes")
    if isinstance(direct, list):
        candidates.extend(item for item in direct if isinstance(item, dict))

    values = payload.get("values")
    if isinstance(values, list):
        candidates.extend(item for item in values if isinstance(item, dict))

    projects = payload.get("projects")
    if isinstance(projects, list):
        for project in projects:
            if not isinstance(project, dict):
                continue
            issue_types = project.get("issuetypes")
            if not isinstance(issue_types, list):
                issue_types = project.get("issueTypes")
            if isinstance(issue_types, list):
                candidates.extend(item for item in issue_types if isinstance(item, dict))

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for issue_type in candidates:
        key = str(issue_type.get("id") or issue_type.get("name") or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue_type)
    return deduped


def _extract_createmeta_fields(payload: Any, issue_type_id: str | None = None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    fields = payload.get("fields")
    if isinstance(fields, dict):
        return fields

    values = payload.get("values")
    if isinstance(values, list):
        fallback: dict[str, Any] | None = None
        for value in values:
            if not isinstance(value, dict):
                continue
            value_fields = value.get("fields")
            if not isinstance(value_fields, dict):
                continue
            if issue_type_id and str(value.get("id")) == issue_type_id:
                return value_fields
            if fallback is None:
                fallback = value_fields
        if fallback is not None:
            return fallback

    projects = payload.get("projects")
    if isinstance(projects, list):
        fallback = None
        for project in projects:
            if not isinstance(project, dict):
                continue
            issue_types = project.get("issuetypes")
            if not isinstance(issue_types, list):
                issue_types = project.get("issueTypes")
            if not isinstance(issue_types, list):
                continue
            for issue_type in issue_types:
                if not isinstance(issue_type, dict):
                    continue
                issue_fields = issue_type.get("fields")
                if not isinstance(issue_fields, dict):
                    continue
                if issue_type_id and str(issue_type.get("id")) == issue_type_id:
                    return issue_fields
                if fallback is None:
                    fallback = issue_fields
        if fallback is not None:
            return fallback

    return None


def _worklog_adjustment_params(
    *,
    adjust_estimate: str | None,
    new_estimate: str | None,
    manual_value: str | None,
    manual_query_name: str,
    allow_manual: bool,
) -> dict[str, str]:
    params: dict[str, str] = {}
    if adjust_estimate is None:
        if new_estimate or manual_value:
            raise typer.Exit(
                code=_fail("--new-estimate and manual estimate flags require --adjust-estimate.")
            )
        return params

    allowed = {"new", "leave", "auto"}
    if allow_manual:
        allowed.add("manual")
    if adjust_estimate not in allowed:
        values = ", ".join(sorted(allowed))
        raise typer.Exit(code=_fail(f"Invalid --adjust-estimate. Allowed values: {values}."))

    params["adjustEstimate"] = adjust_estimate
    if adjust_estimate == "new":
        if not new_estimate:
            raise typer.Exit(code=_fail("--new-estimate is required when --adjust-estimate new."))
        params["newEstimate"] = new_estimate
    elif new_estimate:
        raise typer.Exit(code=_fail("--new-estimate can only be used with --adjust-estimate new."))

    if adjust_estimate == "manual":
        if not manual_value:
            raise typer.Exit(
                code=_fail(
                    f"--{manual_query_name.replace('By', '-by').lower()} is required "
                    "when --adjust-estimate manual."
                )
            )
        params[manual_query_name] = manual_value
    elif manual_value:
        raise typer.Exit(
            code=_fail(
                f"--{manual_query_name.replace('By', '-by').lower()} can only be used "
                "with --adjust-estimate manual."
            )
        )

    return params


@app.command()
def login(
    base_url: str = typer.Option(
        ...,
        "--base-url",
        prompt="Jira base URL (example: https://jira.example.com)",
        help="Base URL for your Jira Data Center instance.",
    ),
    cookie: str | None = typer.Option(
        None,
        "--cookie",
        help="Cookie header value copied from an already logged-in browser session (overrides clipboard).",
    ),
    cookie_from_clipboard: bool = typer.Option(
        True,
        "--cookie-from-clipboard/--no-cookie-from-clipboard",
        help="Read cookie from your system clipboard when --cookie is not provided.",
    ),
    skip_verify: bool = typer.Option(
        False,
        "--skip-verify",
        help="Save the configuration without calling Jira to verify the cookie.",
    ),
) -> None:
    """Save Jira URL + browser cookie and verify auth session."""
    if cookie is None:
        if not cookie_from_clipboard:
            raise typer.Exit(
                code=_fail("No cookie provided. Use --cookie or enable --cookie-from-clipboard.")
            )
        typer.echo("Copy your logged-in Jira Cookie header value to clipboard.")
        typer.prompt("Press Enter to read clipboard", default="", show_default=False)

        attempts = 3
        for idx in range(attempts):
            try:
                candidate = _read_clipboard()
            except ConfigError as exc:
                raise typer.Exit(code=_fail(str(exc)))

            if _looks_like_url(candidate):
                if idx == attempts - 1:
                    raise typer.Exit(
                        code=_fail(
                            "Clipboard content looks like a URL, not a Cookie header value. "
                            "Copy the cookie from browser devtools and try again."
                        )
                    )
                typer.secho(
                    "Clipboard currently looks like a URL. Copy the Cookie header value, then press Enter to retry.",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
                typer.prompt("Retry", default="", show_default=False)
                continue

            cookie = candidate
            break
        else:
            raise typer.Exit(code=_fail("Unable to read a valid cookie value from clipboard."))
    try:
        config = JiraConfig(base_url=normalize_base_url(base_url), cookie=normalize_cookie(cookie))
    except ConfigError as exc:
        raise typer.Exit(code=_fail(str(exc)))

    if not skip_verify:
        try:
            verified, user = _verify_cookie_session(config)
        except ConfigError as exc:
            raise typer.Exit(code=_fail(str(exc)))
        if verified.cookie != config.cookie:
            typer.secho(
                "Using minimized Jira-focused cookie set for CLI requests.",
                fg=typer.colors.YELLOW,
            )
        config = verified
        typer.secho(f"Verified session for user: {user}", fg=typer.colors.GREEN)

    save_config(config)
    typer.secho("Saved configuration to ~/.config/jiradc-cli/config.json", fg=typer.colors.GREEN)


@app.command()
def logout() -> None:
    """Delete locally stored Jira URL + cookie."""
    removed = clear_config()
    if removed:
        typer.secho("Removed local Jira CLI config.", fg=typer.colors.GREEN)
    else:
        typer.echo("No local config found.")


@app.command("whoami")
def whoami(raw: bool = typer.Option(False, "--raw", help="Print full JSON response.")) -> None:
    """Show the currently authenticated Jira user."""

    def run() -> Any:
        return _require_client().request("GET", "/api/2/myself")

    payload = _require_success("whoami", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, dict):
        typer.echo(str(payload))
        return
    typer.echo(f"Name: {payload.get('displayName') or payload.get('name')}")
    typer.echo(f"Username: {payload.get('name')}")
    typer.echo(f"Email: {payload.get('emailAddress')}")
    typer.echo(f"Active: {payload.get('active')}")


@project_app.command("list")
def project_list(raw: bool = typer.Option(False, "--raw", help="Print full JSON response.")) -> None:
    """List visible projects."""

    def run() -> Any:
        return _require_client().request("GET", "/api/2/project")

    payload = _require_success("project list", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, list):
        typer.echo(str(payload))
        return
    for project in payload:
        if not isinstance(project, dict):
            continue
        key = project.get("key")
        name = project.get("name")
        project_type = project.get("projectTypeKey")
        typer.echo(f"{str(key):10} {name} [{project_type}]")


@project_app.command("components")
def project_components(
    project_id_or_key: str = typer.Argument(..., help="Project key or id (example: PROJ)."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """List components for a project."""

    def run() -> Any:
        return _require_client().request("GET", f"/api/2/project/{project_id_or_key}/components")

    payload = _require_success("project components", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, list):
        typer.echo(str(payload))
        return
    for component in payload:
        if not isinstance(component, dict):
            continue
        typer.echo(
            f"{str(component.get('id')):10} {component.get('name')} "
            f"[lead={component.get('leadUserName') or '-'}]"
        )


@project_app.command("versions")
def project_versions(
    project_id_or_key: str = typer.Argument(..., help="Project key or id (example: PROJ)."),
    expand: str | None = typer.Option(None, "--expand", help="Expand response fields."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """List versions for a project."""

    def run() -> Any:
        params = {"expand": expand} if expand else None
        return _require_client().request(
            "GET",
            f"/api/2/project/{project_id_or_key}/versions",
            params=params,
        )

    payload = _require_success("project versions", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, list):
        typer.echo(str(payload))
        return
    for version in payload:
        if not isinstance(version, dict):
            continue
        typer.echo(
            f"{str(version.get('id')):10} {version.get('name')} "
            f"[released={version.get('released')}, archived={version.get('archived')}]"
        )


@issue_app.command("get")
def issue_get(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    expand: str | None = typer.Option(None, "--expand", help="Optional fields to expand."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Get issue details by key."""

    def run() -> Any:
        params = {"expand": expand} if expand else None
        return _require_client().request("GET", f"/api/2/issue/{issue_key}", params=params)

    payload = _require_success("issue get", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, dict):
        typer.echo(str(payload))
        return
    fields = payload.get("fields", {}) if isinstance(payload.get("fields"), dict) else {}
    status_name = None
    status = fields.get("status")
    if isinstance(status, dict):
        status_name = status.get("name")
    summary = fields.get("summary")
    assignee = fields.get("assignee")
    assignee_name = assignee.get("displayName") if isinstance(assignee, dict) else None
    typer.echo(f"Key: {payload.get('key')}")
    typer.echo(f"Summary: {summary}")
    typer.echo(f"Status: {status_name}")
    typer.echo(f"Assignee: {assignee_name}")


@issue_app.command("search")
def issue_search(
    jql: str = typer.Option(..., "--jql", help="JQL query."),
    max_results: int = typer.Option(20, "--max-results", min=1, max=200),
    start_at: int = typer.Option(0, "--start-at", min=0),
    fields: str = typer.Option("summary,status,assignee", "--fields", help="Comma-separated Jira fields."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Search issues with JQL."""

    def run() -> Any:
        params = {
            "jql": jql,
            "maxResults": max_results,
            "startAt": start_at,
            "fields": fields,
        }
        return _require_client().request("GET", "/api/2/search", params=params)

    payload = _require_success("issue search", run)
    if raw:
        _echo_json(payload)
        return
    rows = _extract_issue_rows(payload)
    if not rows:
        _echo_json(payload)
        return
    _print_issue_rows(rows)


@issue_app.command("create")
def issue_create(
    project: str = typer.Option(..., "--project", help="Project key, e.g. PROJ."),
    summary: str = typer.Option(..., "--summary", help="Issue summary."),
    issue_type: str = typer.Option("Task", "--issue-type", help="Jira issue type name."),
    description: str | None = typer.Option(None, "--description", help="Issue description."),
    assignee: str | None = typer.Option(None, "--assignee", help="Username to assign at creation."),
    labels: str | None = typer.Option(None, "--labels", help="Comma-separated labels."),
    reporter: str | None = typer.Option(None, "--reporter", help="Reporter username."),
    due_date: str | None = typer.Option(None, "--due-date", help="Due date in YYYY-MM-DD format."),
    custom_field: list[str] = typer.Option(
        [],
        "--custom-field",
        help=(
            "Custom field assignment in FIELD_ID=VALUE format. "
            "VALUE may be plain text or JSON. Repeat option for multiple fields."
        ),
    ),
    fields_json: str | None = typer.Option(
        None,
        "--fields-json",
        help="JSON object with additional fields, or @<path> to load JSON from file.",
    ),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Create an issue."""

    def run() -> Any:
        fields: dict[str, Any] = {
            "project": {"key": project},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }
        if description:
            fields["description"] = description
        if assignee:
            fields["assignee"] = {"name": assignee}
        if labels is not None:
            fields["labels"] = [l.strip() for l in labels.split(",") if l.strip()]
        if reporter:
            fields["reporter"] = {"name": reporter}
        if due_date:
            fields["duedate"] = due_date
        fields.update(_collect_issue_create_extra_fields(custom_field, fields_json))
        return _require_client().request("POST", "/api/2/issue", json_body={"fields": fields})

    payload = _require_success("issue create", run)
    if raw:
        _echo_json(payload)
        return
    if isinstance(payload, dict):
        typer.echo(f"Created issue: {payload.get('key')} (id={payload.get('id')})")
    else:
        typer.echo(str(payload))


@issue_app.command("createmeta-types")
def issue_create_meta_types(
    project: str = typer.Option(..., "--project", help="Project key or id."),
    max_results: int = typer.Option(50, "--max-results", min=1),
    start_at: int = typer.Option(0, "--start-at", min=0),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """List issue types available when creating issues in a project."""

    def run() -> Any:
        client = _require_client()
        params = {"maxResults": max_results, "startAt": start_at}
        payload = client.request(
            "GET",
            f"/api/2/issue/createmeta/{project}/issuetypes",
            params=params,
        )
        if _extract_issue_types(payload):
            return payload
        return client.request(
            "GET",
            "/api/2/issue/createmeta",
            params={"projectKeys": project, "expand": "projects.issuetypes"},
        )

    payload = _require_success("issue createmeta-types", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, dict):
        typer.echo(str(payload))
        return
    issue_types = _extract_issue_types(payload)
    if not issue_types:
        _echo_json(payload)
        return
    for issue_type in issue_types:
        if not isinstance(issue_type, dict):
            continue
        typer.echo(
            f"{str(issue_type.get('id')):8} {issue_type.get('name')} "
            f"[subtask={issue_type.get('subtask')}]"
        )


@issue_app.command("createmeta-fields")
def issue_create_meta_fields(
    project: str = typer.Option(..., "--project", help="Project key or id."),
    issue_type_id: str = typer.Option(..., "--issue-type-id", help="Issue type id."),
    max_results: int = typer.Option(200, "--max-results", min=1),
    start_at: int = typer.Option(0, "--start-at", min=0),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """List field metadata for issue creation in a project/issue type."""

    def run() -> Any:
        client = _require_client()
        params = {"maxResults": max_results, "startAt": start_at}
        payload = client.request(
            "GET",
            f"/api/2/issue/createmeta/{project}/issuetypes/{issue_type_id}",
            params=params,
        )
        if _extract_createmeta_fields(payload, issue_type_id) is not None:
            return payload
        return client.request(
            "GET",
            "/api/2/issue/createmeta",
            params={
                "projectKeys": project,
                "issuetypeIds": issue_type_id,
                "expand": "projects.issuetypes.fields",
            },
        )

    payload = _require_success("issue createmeta-fields", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, dict):
        typer.echo(str(payload))
        return
    fields = _extract_createmeta_fields(payload, issue_type_id)
    if not isinstance(fields, dict):
        _echo_json(payload)
        return
    for field_id, meta in fields.items():
        if not isinstance(meta, dict):
            continue
        required = "required" if meta.get("required") else "optional"
        operations = meta.get("operations")
        op_text = ",".join(str(op) for op in operations) if isinstance(operations, list) else "-"
        typer.echo(f"{field_id:28} {meta.get('name')} [{required}] ops={op_text}")


@issue_app.command("editmeta")
def issue_editmeta(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Show editable fields metadata for an issue."""

    def run() -> Any:
        return _require_client().request("GET", f"/api/2/issue/{issue_key}/editmeta")

    payload = _require_success("issue editmeta", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, dict):
        typer.echo(str(payload))
        return
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        _echo_json(payload)
        return
    for field_id, meta in fields.items():
        if not isinstance(meta, dict):
            continue
        required = "required" if meta.get("required") else "optional"
        operations = meta.get("operations")
        op_text = ",".join(str(op) for op in operations) if isinstance(operations, list) else "-"
        typer.echo(f"{field_id:28} {meta.get('name')} [{required}] ops={op_text}")


@issue_app.command("edit")
def issue_edit(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    summary: str | None = typer.Option(None, "--summary", help="Set summary."),
    description: str | None = typer.Option(None, "--description", help="Set description."),
    priority: str | None = typer.Option(None, "--priority", help="Set priority name."),
    assignee: str | None = typer.Option(None, "--assignee", help="Set assignee username."),
    clear_assignee: bool = typer.Option(False, "--clear-assignee", help="Set assignee to unassigned."),
    labels: str | None = typer.Option(None, "--labels", help="Comma-separated labels to replace existing labels."),
    reporter: str | None = typer.Option(None, "--reporter", help="Reporter username."),
    due_date: str | None = typer.Option(None, "--due-date", help="Due date in YYYY-MM-DD format."),
    custom_field: list[str] = typer.Option(
        [],
        "--custom-field",
        help=(
            "Custom field assignment in FIELD_ID=VALUE format. "
            "VALUE may be plain text or JSON. Repeat option for multiple fields."
        ),
    ),
    fields_json: str | None = typer.Option(
        None,
        "--fields-json",
        help="JSON object with additional fields, or @<path> to load JSON from file.",
    ),
    notify_users: bool = typer.Option(True, "--notify-users/--no-notify-users", help="Notify watchers by email."),
) -> None:
    """Edit issue fields (summary/description/priority/assignee/labels)."""
    if assignee and clear_assignee:
        raise typer.Exit(code=_fail("Use either --assignee or --clear-assignee, not both."))

    fields: dict[str, Any] = {}
    if summary is not None:
        fields["summary"] = summary
    if description is not None:
        fields["description"] = description
    if priority is not None:
        fields["priority"] = {"name": priority}
    if assignee is not None:
        fields["assignee"] = {"name": assignee}
    if clear_assignee:
        fields["assignee"] = None
    label_values = _split_csv(labels)
    if labels is not None:
        fields["labels"] = label_values or []
    if reporter is not None:
        fields["reporter"] = {"name": reporter}
    if due_date is not None:
        fields["duedate"] = due_date
    fields.update(_collect_issue_create_extra_fields(custom_field, fields_json))

    if not fields:
        raise typer.Exit(
            code=_fail(
                "No updates provided. Use at least one of --summary, --description, "
                "--priority, --assignee, --clear-assignee, --labels, --reporter, "
                "--due-date, or --custom-field."
            )
        )

    def run() -> Any:
        params = {"notifyUsers": str(notify_users).lower()}
        return _require_client().request(
            "PUT",
            f"/api/2/issue/{issue_key}",
            params=params,
            json_body={"fields": fields},
        )

    _require_success("issue edit", run)
    typer.secho(f"Updated {issue_key}: {', '.join(sorted(fields.keys()))}", fg=typer.colors.GREEN)


@issue_app.command("comments")
def issue_comments(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """List comments for an issue."""

    def run() -> Any:
        return _require_client().request("GET", f"/api/2/issue/{issue_key}/comment")

    payload = _require_success("issue comments", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, dict):
        typer.echo(str(payload))
        return
    comments = payload.get("comments")
    if not isinstance(comments, list):
        _echo_json(payload)
        return
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        author = comment.get("author") if isinstance(comment.get("author"), dict) else {}
        created = comment.get("created")
        body = str(comment.get("body", "")).replace("\n", " ")
        trimmed_body = body[:180] + ("..." if len(body) > 180 else "")
        typer.echo(f"[{comment.get('id')}] {author.get('displayName') or author.get('name')} @ {created}")
        typer.echo(f"  {trimmed_body}")


@issue_app.command("comment-add")
def issue_comment_add(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    body: str = typer.Option(..., "--body", prompt=True, help="Comment body."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Add a comment to an issue."""

    def run() -> Any:
        return _require_client().request(
            "POST",
            f"/api/2/issue/{issue_key}/comment",
            json_body={"body": body},
        )

    payload = _require_success("issue comment-add", run)
    if raw:
        _echo_json(payload)
        return
    if isinstance(payload, dict):
        typer.echo(f"Added comment {payload.get('id')} to {issue_key}")
    else:
        typer.echo(str(payload))


@issue_app.command("comment-get")
def issue_comment_get(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    comment_id: str = typer.Argument(..., help="Comment id."),
    expand: str | None = typer.Option(None, "--expand", help="Optional expand flags."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Get one comment by id."""

    def run() -> Any:
        params = {"expand": expand} if expand else None
        return _require_client().request(
            "GET",
            f"/api/2/issue/{issue_key}/comment/{comment_id}",
            params=params,
        )

    payload = _require_success("issue comment-get", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, dict):
        typer.echo(str(payload))
        return
    author = payload.get("author") if isinstance(payload.get("author"), dict) else {}
    typer.echo(f"Comment: {payload.get('id')}")
    typer.echo(f"Author: {author.get('displayName') or author.get('name')}")
    typer.echo(f"Created: {payload.get('created')}")
    typer.echo(str(payload.get("body") or ""))


@issue_app.command("comment-update")
def issue_comment_update(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    comment_id: str = typer.Argument(..., help="Comment id."),
    body: str = typer.Option(..., "--body", prompt=True, help="Updated comment body."),
    expand: str | None = typer.Option(None, "--expand", help="Optional expand flags."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Update one comment by id."""

    def run() -> Any:
        params = {"expand": expand} if expand else None
        return _require_client().request(
            "PUT",
            f"/api/2/issue/{issue_key}/comment/{comment_id}",
            params=params,
            json_body={"body": body},
        )

    payload = _require_success("issue comment-update", run)
    if raw:
        _echo_json(payload)
        return
    if isinstance(payload, dict):
        typer.echo(f"Updated comment {payload.get('id')} on {issue_key}")
    else:
        typer.echo(f"Updated comment {comment_id} on {issue_key}")


@issue_app.command("comment-delete")
def issue_comment_delete(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    comment_id: str = typer.Argument(..., help="Comment id."),
) -> None:
    """Delete one comment by id."""

    def run() -> Any:
        return _require_client().request("DELETE", f"/api/2/issue/{issue_key}/comment/{comment_id}")

    _require_success("issue comment-delete", run)
    typer.secho(f"Deleted comment {comment_id} from {issue_key}", fg=typer.colors.GREEN)


@issue_app.command("attachment-add")
def issue_attachment_add(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    file_paths: list[Path] = typer.Option(
        ...,
        "--file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Attachment file path. Repeat flag to upload multiple files.",
    ),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Upload one or more attachments to an issue."""

    def run() -> Any:
        handles = []
        multipart_files = []
        try:
            for path in file_paths:
                handle = path.open("rb")
                handles.append(handle)
                multipart_files.append(("file", (path.name, handle, "application/octet-stream")))
            return _require_client().request(
                "POST",
                f"/api/2/issue/{issue_key}/attachments",
                files=multipart_files,
                headers={"X-Atlassian-Token": "no-check"},
            )
        finally:
            for handle in handles:
                handle.close()

    payload = _require_success("issue attachment-add", run)
    if raw:
        _echo_json(payload)
        return
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            author = item.get("author") if isinstance(item.get("author"), dict) else {}
            typer.echo(
                f"[{item.get('id')}] {item.get('filename')} "
                f"({item.get('size')} bytes) by {author.get('displayName') or author.get('name')}"
            )
        return
    typer.echo(str(payload))


@issue_app.command("transitions")
def issue_transitions(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """List available transitions for an issue."""

    def run() -> Any:
        return _require_client().request("GET", f"/api/2/issue/{issue_key}/transitions")

    payload = _require_success("issue transitions", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, dict):
        typer.echo(str(payload))
        return
    transitions = payload.get("transitions")
    if not isinstance(transitions, list):
        _echo_json(payload)
        return
    for transition in transitions:
        if not isinstance(transition, dict):
            continue
        to_state = transition.get("to") if isinstance(transition.get("to"), dict) else {}
        typer.echo(f"{transition.get('id'):>4}  {transition.get('name')} -> {to_state.get('name')}")


@issue_app.command("transition")
def issue_transition(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    transition_id: str = typer.Option(..., "--id", help="Transition id from 'issue transitions'."),
    comment: str | None = typer.Option(None, "--comment", help="Optional transition comment."),
) -> None:
    """Perform a transition on an issue."""

    def run() -> Any:
        payload: dict[str, Any] = {"transition": {"id": transition_id}}
        if comment:
            payload["update"] = {"comment": [{"add": {"body": comment}}]}
        return _require_client().request(
            "POST",
            f"/api/2/issue/{issue_key}/transitions",
            json_body=payload,
        )

    _require_success("issue transition", run)
    typer.secho(f"Transitioned {issue_key} via id {transition_id}", fg=typer.colors.GREEN)


@issue_app.command("assign")
def issue_assign(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    username: str = typer.Option(..., "--username", prompt=True, help="Jira username."),
) -> None:
    """Assign an issue to a user."""

    def run() -> Any:
        return _require_client().request(
            "PUT",
            f"/api/2/issue/{issue_key}/assignee",
            json_body={"name": username},
        )

    _require_success("issue assign", run)
    typer.secho(f"Assigned {issue_key} to {username}", fg=typer.colors.GREEN)


@issue_app.command("watchers")
def issue_watchers(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Show watchers for an issue."""

    def run() -> Any:
        return _require_client().request("GET", f"/api/2/issue/{issue_key}/watchers")

    payload = _require_success("issue watchers", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, dict):
        typer.echo(str(payload))
        return
    typer.echo(f"Watching: {payload.get('isWatching')}")
    typer.echo(f"Watch count: {payload.get('watchCount')}")
    watchers = payload.get("watchers")
    if isinstance(watchers, list):
        for watcher in watchers:
            if not isinstance(watcher, dict):
                continue
            typer.echo(f"- {watcher.get('displayName') or watcher.get('name')}")


@issue_app.command("watcher-add")
def issue_watcher_add(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    username: str | None = typer.Option(
        None,
        "--username",
        help="Username to add. Omit to add current user.",
    ),
) -> None:
    """Add watcher to an issue."""

    def run() -> Any:
        params = {"userName": username} if username else None
        return _require_client().request("POST", f"/api/2/issue/{issue_key}/watchers", params=params)

    _require_success("issue watcher-add", run)
    target = username or "current user"
    typer.secho(f"Added watcher {target} to {issue_key}", fg=typer.colors.GREEN)


@issue_app.command("watcher-remove")
def issue_watcher_remove(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    username: str = typer.Option(..., "--username", help="Username to remove from watchers."),
) -> None:
    """Remove watcher from an issue."""

    def run() -> Any:
        return _require_client().request(
            "DELETE",
            f"/api/2/issue/{issue_key}/watchers",
            params={"userName": username},
        )

    _require_success("issue watcher-remove", run)
    typer.secho(f"Removed watcher {username} from {issue_key}", fg=typer.colors.GREEN)


@issue_app.command("votes")
def issue_votes(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Show votes for an issue."""

    def run() -> Any:
        return _require_client().request("GET", f"/api/2/issue/{issue_key}/votes")

    payload = _require_success("issue votes", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, dict):
        typer.echo(str(payload))
        return
    typer.echo(f"Votes: {payload.get('votes')}")
    typer.echo(f"Has voted: {payload.get('hasVoted')}")


@issue_app.command("vote-add")
def issue_vote_add(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Add current user vote to an issue."""

    def run() -> Any:
        return _require_client().request("POST", f"/api/2/issue/{issue_key}/votes")

    payload = _require_success("issue vote-add", run)
    if raw and payload is not None:
        _echo_json(payload)
        return
    typer.secho(f"Added vote to {issue_key}", fg=typer.colors.GREEN)


@issue_app.command("vote-remove")
def issue_vote_remove(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
) -> None:
    """Remove current user vote from an issue."""

    def run() -> Any:
        return _require_client().request("DELETE", f"/api/2/issue/{issue_key}/votes")

    _require_success("issue vote-remove", run)
    typer.secho(f"Removed vote from {issue_key}", fg=typer.colors.GREEN)


@issue_app.command("worklogs")
def issue_worklogs(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """List worklogs for an issue."""

    def run() -> Any:
        return _require_client().request("GET", f"/api/2/issue/{issue_key}/worklog")

    payload = _require_success("issue worklogs", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, dict):
        typer.echo(str(payload))
        return
    worklogs = payload.get("worklogs")
    if not isinstance(worklogs, list):
        _echo_json(payload)
        return
    for worklog in worklogs:
        if not isinstance(worklog, dict):
            continue
        author = worklog.get("author") if isinstance(worklog.get("author"), dict) else {}
        typer.echo(
            f"[{worklog.get('id')}] {author.get('displayName') or author.get('name')} "
            f"{worklog.get('timeSpent')} @ {worklog.get('started')}"
        )
        comment = worklog.get("comment")
        if isinstance(comment, str) and comment:
            typer.echo(f"  {comment}")


@issue_app.command("worklog-get")
def issue_worklog_get(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    worklog_id: str = typer.Argument(..., help="Worklog id."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Get a worklog by id."""

    def run() -> Any:
        return _require_client().request("GET", f"/api/2/issue/{issue_key}/worklog/{worklog_id}")

    payload = _require_success("issue worklog-get", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, dict):
        typer.echo(str(payload))
        return
    author = payload.get("author") if isinstance(payload.get("author"), dict) else {}
    typer.echo(f"Worklog: {payload.get('id')}")
    typer.echo(f"Author: {author.get('displayName') or author.get('name')}")
    typer.echo(f"Started: {payload.get('started')}")
    typer.echo(f"Time: {payload.get('timeSpent') or payload.get('timeSpentSeconds')}")
    if payload.get("comment"):
        typer.echo(f"Comment: {payload.get('comment')}")


@issue_app.command("worklog-add")
def issue_worklog_add(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    time_spent: str = typer.Option(..., "--time-spent", help="Time spent (example: 2h 30m)."),
    comment: str | None = typer.Option(None, "--comment", help="Worklog comment."),
    started: str | None = typer.Option(
        None,
        "--started",
        help="Start timestamp (example: 2026-02-23T12:00:00.000+0000).",
    ),
    adjust_estimate: str | None = typer.Option(
        None,
        "--adjust-estimate",
        help="One of: new, leave, manual, auto.",
    ),
    new_estimate: str | None = typer.Option(None, "--new-estimate", help="Used with --adjust-estimate new."),
    reduce_by: str | None = typer.Option(None, "--reduce-by", help="Used with --adjust-estimate manual."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Add a worklog entry to an issue."""

    params = _worklog_adjustment_params(
        adjust_estimate=adjust_estimate,
        new_estimate=new_estimate,
        manual_value=reduce_by,
        manual_query_name="reduceBy",
        allow_manual=True,
    )

    payload: dict[str, Any] = {"timeSpent": time_spent}
    if comment is not None:
        payload["comment"] = comment
    if started is not None:
        payload["started"] = started

    def run() -> Any:
        return _require_client().request(
            "POST",
            f"/api/2/issue/{issue_key}/worklog",
            params=params,
            json_body=payload,
        )

    response = _require_success("issue worklog-add", run)
    if raw:
        _echo_json(response)
        return
    if isinstance(response, dict):
        typer.echo(f"Added worklog {response.get('id')} to {issue_key}")
    else:
        typer.echo(f"Added worklog to {issue_key}")


@issue_app.command("worklog-update")
def issue_worklog_update(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    worklog_id: str = typer.Argument(..., help="Worklog id."),
    time_spent: str | None = typer.Option(None, "--time-spent", help="Updated time spent (example: 1h)."),
    comment: str | None = typer.Option(None, "--comment", help="Updated comment."),
    started: str | None = typer.Option(None, "--started", help="Updated started timestamp."),
    adjust_estimate: str | None = typer.Option(
        None,
        "--adjust-estimate",
        help="One of: new, leave, auto.",
    ),
    new_estimate: str | None = typer.Option(None, "--new-estimate", help="Used with --adjust-estimate new."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Update an existing worklog entry."""

    params = _worklog_adjustment_params(
        adjust_estimate=adjust_estimate,
        new_estimate=new_estimate,
        manual_value=None,
        manual_query_name="reduceBy",
        allow_manual=False,
    )

    payload: dict[str, Any] = {}
    if time_spent is not None:
        payload["timeSpent"] = time_spent
    if comment is not None:
        payload["comment"] = comment
    if started is not None:
        payload["started"] = started

    if not payload:
        raise typer.Exit(
            code=_fail("Provide at least one update field: --time-spent, --comment, or --started.")
        )

    def run() -> Any:
        return _require_client().request(
            "PUT",
            f"/api/2/issue/{issue_key}/worklog/{worklog_id}",
            params=params,
            json_body=payload,
        )

    response = _require_success("issue worklog-update", run)
    if raw:
        _echo_json(response)
        return
    if isinstance(response, dict):
        typer.echo(f"Updated worklog {response.get('id')} on {issue_key}")
    else:
        typer.echo(f"Updated worklog {worklog_id} on {issue_key}")


@issue_app.command("worklog-delete")
def issue_worklog_delete(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    worklog_id: str = typer.Argument(..., help="Worklog id."),
    adjust_estimate: str | None = typer.Option(
        None,
        "--adjust-estimate",
        help="One of: new, leave, manual, auto.",
    ),
    new_estimate: str | None = typer.Option(None, "--new-estimate", help="Used with --adjust-estimate new."),
    increase_by: str | None = typer.Option(None, "--increase-by", help="Used with --adjust-estimate manual."),
) -> None:
    """Delete a worklog entry."""

    params = _worklog_adjustment_params(
        adjust_estimate=adjust_estimate,
        new_estimate=new_estimate,
        manual_value=increase_by,
        manual_query_name="increaseBy",
        allow_manual=True,
    )

    def run() -> Any:
        return _require_client().request(
            "DELETE",
            f"/api/2/issue/{issue_key}/worklog/{worklog_id}",
            params=params,
        )

    _require_success("issue worklog-delete", run)
    typer.secho(f"Deleted worklog {worklog_id} from {issue_key}", fg=typer.colors.GREEN)


@issue_app.command("picker")
def issue_picker(
    query: str = typer.Option(..., "--query", help="Issue query text."),
    current_project_id: str | None = typer.Option(None, "--current-project-id", help="Current project id."),
    current_issue_key: str | None = typer.Option(None, "--current-issue-key", help="Current issue key."),
    current_jql: str | None = typer.Option(None, "--current-jql", help="Current JQL context."),
    show_subtasks: bool | None = typer.Option(
        None,
        "--show-subtasks/--no-show-subtasks",
        help="Include subtasks in suggestions.",
    ),
    show_subtask_parent: bool | None = typer.Option(
        None,
        "--show-subtask-parent/--no-show-subtask-parent",
        help="Include subtask parent in suggestions.",
    ),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Get issue auto-complete suggestions."""

    def run() -> Any:
        params: dict[str, Any] = {"query": query}
        if current_project_id is not None:
            params["currentProjectId"] = current_project_id
        if current_issue_key is not None:
            params["currentIssueKey"] = current_issue_key
        if current_jql is not None:
            params["currentJQL"] = current_jql
        if show_subtasks is not None:
            params["showSubTasks"] = str(show_subtasks).lower()
        if show_subtask_parent is not None:
            params["showSubTaskParent"] = str(show_subtask_parent).lower()
        return _require_client().request("GET", "/api/2/issue/picker", params=params)

    payload = _require_success("issue picker", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, dict):
        typer.echo(str(payload))
        return

    sections = payload.get("sections")
    if not isinstance(sections, list):
        _echo_json(payload)
        return

    for section in sections:
        if not isinstance(section, dict):
            continue
        label = section.get("label") or section.get("id") or "section"
        typer.echo(f"[{label}]")
        issues = section.get("issues")
        if not isinstance(issues, list):
            continue
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            key = issue.get("key") or issue.get("keyHtml")
            summary = issue.get("summary") or issue.get("summaryText") or issue.get("summaryHtml")
            typer.echo(f"  {key}: {summary}")


@issue_app.command("link-types")
def issue_link_types(
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """List available issue link types."""

    def run() -> Any:
        return _require_client().request("GET", "/api/2/issueLinkType")

    payload = _require_success("issue link-types", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, dict):
        typer.echo(str(payload))
        return
    link_types = payload.get("issueLinkTypes")
    if not isinstance(link_types, list):
        _echo_json(payload)
        return
    for link_type in link_types:
        if not isinstance(link_type, dict):
            continue
        typer.echo(
            f"{str(link_type.get('id')):8} {link_type.get('name')} "
            f"(outward={link_type.get('outward')}, inward={link_type.get('inward')})"
        )


@issue_app.command("link-create")
def issue_link_create(
    link_type: str = typer.Option(..., "--type", help="Issue link type name (example: Blocks)."),
    inward_issue: str = typer.Option(..., "--inward-issue", help="Issue key/id for inward side."),
    outward_issue: str = typer.Option(..., "--outward-issue", help="Issue key/id for outward side."),
    comment: str | None = typer.Option(None, "--comment", help="Optional comment on inward issue."),
) -> None:
    """Create an issue link between two issues."""

    body: dict[str, Any] = {
        "type": {"name": link_type},
        "inwardIssue": {"key": inward_issue},
        "outwardIssue": {"key": outward_issue},
    }
    if comment is not None:
        body["comment"] = {"body": comment}

    def run() -> Any:
        return _require_client().request("POST", "/api/2/issueLink", json_body=body)

    _require_success("issue link-create", run)
    typer.secho(
        f"Linked {inward_issue} <-> {outward_issue} with type {link_type}",
        fg=typer.colors.GREEN,
    )


@filter_app.command("favourites")
def filter_favourites(
    expand: str | None = typer.Option(None, "--expand", help="Optional expand values."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """List favourite filters for current user."""

    def run() -> Any:
        params = {"expand": expand} if expand else None
        return _require_client().request("GET", "/api/2/filter/favourite", params=params)

    payload = _require_success("filter favourites", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, list):
        typer.echo(str(payload))
        return
    for filt in payload:
        if not isinstance(filt, dict):
            continue
        typer.echo(f"{str(filt.get('id')):8} {filt.get('name')} -> {filt.get('jql')}")


@filter_app.command("get")
def filter_get(
    filter_id: str = typer.Argument(..., help="Filter id."),
    expand: str | None = typer.Option(None, "--expand", help="Optional expand values."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Get a filter by id."""

    def run() -> Any:
        params = {"expand": expand} if expand else None
        return _require_client().request("GET", f"/api/2/filter/{filter_id}", params=params)

    payload = _require_success("filter get", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, dict):
        typer.echo(str(payload))
        return
    owner_name = None
    owner = payload.get("owner")
    if isinstance(owner, dict):
        owner_name = owner.get("displayName") or owner.get("name")
    typer.echo(f"ID: {payload.get('id')}")
    typer.echo(f"Name: {payload.get('name')}")
    typer.echo(f"JQL: {payload.get('jql')}")
    typer.echo(f"Owner: {owner_name}")


@filter_app.command("create")
def filter_create(
    name: str = typer.Option(..., "--name", help="Filter name."),
    jql: str = typer.Option(..., "--jql", help="Filter JQL."),
    description: str | None = typer.Option(None, "--description", help="Filter description."),
    favourite: bool | None = typer.Option(
        None,
        "--favourite/--no-favourite",
        help="Mark as favourite when supported by server.",
    ),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Create a filter."""

    body: dict[str, Any] = {"name": name, "jql": jql}
    if description is not None:
        body["description"] = description
    if favourite is not None:
        body["favourite"] = favourite

    def run() -> Any:
        return _require_client().request("POST", "/api/2/filter", json_body=body)

    payload = _require_success("filter create", run)
    if raw:
        _echo_json(payload)
        return
    if isinstance(payload, dict):
        typer.echo(f"Created filter {payload.get('id')}: {payload.get('name')}")
    else:
        typer.echo(str(payload))


@filter_app.command("update")
def filter_update(
    filter_id: str = typer.Argument(..., help="Filter id."),
    name: str | None = typer.Option(None, "--name", help="New filter name."),
    jql: str | None = typer.Option(None, "--jql", help="New filter JQL."),
    description: str | None = typer.Option(None, "--description", help="New filter description."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Update a filter."""

    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if jql is not None:
        body["jql"] = jql
    if description is not None:
        body["description"] = description

    if not body:
        raise typer.Exit(code=_fail("Provide at least one field: --name, --jql, --description."))

    def run() -> Any:
        return _require_client().request("PUT", f"/api/2/filter/{filter_id}", json_body=body)

    payload = _require_success("filter update", run)
    if raw:
        _echo_json(payload)
        return
    if isinstance(payload, dict):
        typer.echo(f"Updated filter {payload.get('id')}: {payload.get('name')}")
    else:
        typer.echo(f"Updated filter {filter_id}")


@jql_app.command("suggest")
def jql_suggest(
    field_name: str | None = typer.Option(None, "--field-name", help="JQL field name."),
    field_value: str | None = typer.Option(None, "--field-value", help="JQL field value prefix."),
    predicate_name: str | None = typer.Option(None, "--predicate-name", help="Predicate name."),
    predicate_value: str | None = typer.Option(None, "--predicate-value", help="Predicate value."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Get JQL auto-complete suggestions."""

    def run() -> Any:
        params: dict[str, Any] = {}
        if field_name is not None:
            params["fieldName"] = field_name
        if field_value is not None:
            params["fieldValue"] = field_value
        if predicate_name is not None:
            params["predicateName"] = predicate_name
        if predicate_value is not None:
            params["predicateValue"] = predicate_value
        return _require_client().request(
            "GET",
            "/api/2/jql/autocompletedata/suggestions",
            params=params if params else None,
        )

    payload = _require_success("jql suggest", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, dict):
        typer.echo(str(payload))
        return
    results = payload.get("results")
    if not isinstance(results, list):
        _echo_json(payload)
        return
    for result in results:
        if not isinstance(result, dict):
            continue
        value = result.get("value") or result.get("displayName") or result.get("name")
        if value is not None:
            typer.echo(str(value))


@board_app.command("list")
def agile_board_list(
    max_results: int = typer.Option(50, "--max-results", min=1),
    start_at: int = typer.Option(0, "--start-at", min=0),
    name: str | None = typer.Option(None, "--name", help="Board name filter."),
    project: str | None = typer.Option(None, "--project", help="Project key or id filter."),
    board_type: str | None = typer.Option(
        None,
        "--type",
        help="Comma-separated board types (scrum,kanban).",
    ),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """List Agile boards visible to user."""

    def run() -> Any:
        params: dict[str, Any] = {
            "maxResults": max_results,
            "startAt": start_at,
        }
        if name:
            params["name"] = name
        if project:
            params["projectKeyOrId"] = project
        types = _split_csv(board_type)
        if types:
            params["type"] = types
        return _require_client().request("GET", "/agile/1.0/board", params=params)

    payload = _require_success("agile board list", run)
    if raw:
        _echo_json(payload)
        return
    if isinstance(payload, dict):
        values = payload.get("values")
        if isinstance(values, list):
            for board in values:
                if not isinstance(board, dict):
                    continue
                typer.echo(f"{str(board.get('id')):8} {board.get('type'):8} {board.get('name')}")
            return
    _echo_json(payload)


@board_app.command("backlog")
def agile_board_backlog(
    board_id: int = typer.Argument(..., help="Board id."),
    jql: str | None = typer.Option(None, "--jql", help="Additional JQL filter."),
    fields: str = typer.Option(
        "summary,status,assignee",
        "--fields",
        help="Comma-separated fields.",
    ),
    max_results: int = typer.Option(50, "--max-results", min=1),
    start_at: int = typer.Option(0, "--start-at", min=0),
    validate_query: bool | None = typer.Option(
        None,
        "--validate-query/--no-validate-query",
        help="Validate JQL query.",
    ),
    expand: str | None = typer.Option(None, "--expand", help="Optional expand fields."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """List backlog issues for a board."""

    def run() -> Any:
        params: dict[str, Any] = {
            "maxResults": max_results,
            "startAt": start_at,
            "fields": _split_csv(fields) or ["summary", "status", "assignee"],
        }
        if jql is not None:
            params["jql"] = jql
        if validate_query is not None:
            params["validateQuery"] = validate_query
        if expand is not None:
            params["expand"] = expand
        return _require_client().request("GET", f"/agile/1.0/board/{board_id}/backlog", params=params)

    payload = _require_success("agile board backlog", run)
    if raw:
        _echo_json(payload)
        return
    rows = _extract_issue_rows(payload)
    if rows:
        _print_issue_rows(rows)
        return
    _echo_json(payload)


@board_app.command("sprints")
def agile_board_sprints(
    board_id: int = typer.Argument(..., help="Board id."),
    state: str | None = typer.Option(
        None,
        "--state",
        help="Comma-separated sprint states (active,future,closed).",
    ),
    max_results: int = typer.Option(50, "--max-results", min=1),
    start_at: int = typer.Option(0, "--start-at", min=0),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """List sprints for a board."""

    def run() -> Any:
        params: dict[str, Any] = {
            "maxResults": max_results,
            "startAt": start_at,
        }
        states = _split_csv(state)
        if states:
            params["state"] = states
        return _require_client().request("GET", f"/agile/1.0/board/{board_id}/sprint", params=params)

    payload = _require_success("agile board sprints", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, dict):
        typer.echo(str(payload))
        return
    values = payload.get("values")
    if not isinstance(values, list):
        _echo_json(payload)
        return
    for sprint in values:
        if not isinstance(sprint, dict):
            continue
        typer.echo(
            f"{str(sprint.get('id')):8} {str(sprint.get('state')):8} "
            f"{sprint.get('name')}"
        )


@sprint_app.command("issues")
def agile_sprint_issues(
    sprint_id: int = typer.Argument(..., help="Sprint id."),
    jql: str | None = typer.Option(None, "--jql", help="Additional JQL filter."),
    fields: str = typer.Option("summary,status,assignee", "--fields", help="Comma-separated fields."),
    max_results: int = typer.Option(50, "--max-results", min=1),
    start_at: int = typer.Option(0, "--start-at", min=0),
    validate_query: bool | None = typer.Option(
        None,
        "--validate-query/--no-validate-query",
        help="Validate JQL query.",
    ),
    expand: str | None = typer.Option(None, "--expand", help="Optional expand fields."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """List issues in a sprint."""

    def run() -> Any:
        params: dict[str, Any] = {
            "maxResults": max_results,
            "startAt": start_at,
            "fields": _split_csv(fields) or ["summary", "status", "assignee"],
        }
        if jql is not None:
            params["jql"] = jql
        if validate_query is not None:
            params["validateQuery"] = validate_query
        if expand is not None:
            params["expand"] = expand
        return _require_client().request("GET", f"/agile/1.0/sprint/{sprint_id}/issue", params=params)

    payload = _require_success("agile sprint issues", run)
    if raw:
        _echo_json(payload)
        return
    rows = _extract_issue_rows(payload)
    if rows:
        _print_issue_rows(rows)
        return
    _echo_json(payload)


@sprint_app.command("move-issues")
def agile_sprint_move_issues(
    sprint_id: int = typer.Argument(..., help="Sprint id."),
    issues: list[str] = typer.Option(
        ...,
        "--issue",
        help="Issue key/id to move. Repeat for multiple issues.",
    ),
) -> None:
    """Move issues into a sprint."""

    if len(issues) > 50:
        raise typer.Exit(code=_fail("At most 50 issues can be moved per request."))

    def run() -> Any:
        return _require_client().request(
            "POST",
            f"/agile/1.0/sprint/{sprint_id}/issue",
            json_body={"issues": issues},
        )

    _require_success("agile sprint move-issues", run)
    typer.secho(
        f"Moved {len(issues)} issue(s) to sprint {sprint_id}",
        fg=typer.colors.GREEN,
    )


@agile_issue_app.command("rank")
def agile_issue_rank(
    issues: list[str] = typer.Option(
        ...,
        "--issue",
        help="Issue key/id to rank. Repeat for multiple issues.",
    ),
    rank_before_issue: str | None = typer.Option(None, "--before", help="Rank before this issue."),
    rank_after_issue: str | None = typer.Option(None, "--after", help="Rank after this issue."),
    rank_custom_field_id: int | None = typer.Option(
        None,
        "--rank-custom-field-id",
        help="Custom rank field id.",
    ),
    raw: bool = typer.Option(False, "--raw", help="Print response body when provided."),
) -> None:
    """Rank issues before or after another issue."""

    if len(issues) > 50:
        raise typer.Exit(code=_fail("At most 50 issues can be ranked per request."))
    if bool(rank_before_issue) == bool(rank_after_issue):
        raise typer.Exit(code=_fail("Use exactly one of --before or --after."))

    body: dict[str, Any] = {"issues": issues}
    if rank_before_issue:
        body["rankBeforeIssue"] = rank_before_issue
    if rank_after_issue:
        body["rankAfterIssue"] = rank_after_issue
    if rank_custom_field_id is not None:
        body["rankCustomFieldId"] = rank_custom_field_id

    def run() -> Any:
        return _require_client().request("PUT", "/agile/1.0/issue/rank", json_body=body)

    payload = _require_success("agile issue rank", run)
    if raw and payload is not None:
        _echo_json(payload)
        return
    if payload is None:
        typer.secho(f"Ranked {len(issues)} issue(s)", fg=typer.colors.GREEN)
        return
    _echo_json(payload)


@agile_issue_app.command("estimation")
def agile_issue_estimation(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    board_id: int = typer.Option(..., "--board-id", help="Board id."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Get issue estimation value for a board."""

    def run() -> Any:
        return _require_client().request(
            "GET",
            f"/agile/1.0/issue/{issue_key}/estimation",
            params={"boardId": board_id},
        )

    payload = _require_success("agile issue estimation", run)
    if raw:
        _echo_json(payload)
        return
    if not isinstance(payload, dict):
        typer.echo(str(payload))
        return
    typer.echo(f"Field: {payload.get('fieldId')}")
    typer.echo(f"Value: {payload.get('value')}")


@agile_issue_app.command("estimation-set")
def agile_issue_estimation_set(
    issue_key: str = typer.Argument(..., help="Issue key (example: PROJ-123)."),
    board_id: int = typer.Option(..., "--board-id", help="Board id."),
    value: str = typer.Option(..., "--value", help="New estimation value."),
    raw: bool = typer.Option(False, "--raw", help="Print full JSON response."),
) -> None:
    """Set issue estimation value for a board."""

    def run() -> Any:
        return _require_client().request(
            "PUT",
            f"/agile/1.0/issue/{issue_key}/estimation",
            params={"boardId": board_id},
            json_body={"value": value},
        )

    payload = _require_success("agile issue estimation-set", run)
    if raw:
        _echo_json(payload)
        return
    if isinstance(payload, dict):
        typer.echo(f"Updated estimation for {issue_key}: {payload.get('value')}")
    else:
        typer.echo(f"Updated estimation for {issue_key}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
