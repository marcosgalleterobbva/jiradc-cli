from __future__ import annotations

import json
import shutil
import subprocess
import sys
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

app.add_typer(project_app, name="project")
app.add_typer(issue_app, name="issue")


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
    if not isinstance(payload, dict):
        typer.echo(str(payload))
        return
    issues = payload.get("issues")
    if not isinstance(issues, list):
        _echo_json(payload)
        return
    for issue in issues:
        if not isinstance(issue, dict):
            continue
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


@issue_app.command("create")
def issue_create(
    project: str = typer.Option(..., "--project", help="Project key, e.g. PROJ."),
    summary: str = typer.Option(..., "--summary", help="Issue summary."),
    issue_type: str = typer.Option("Task", "--issue-type", help="Jira issue type name."),
    description: str | None = typer.Option(None, "--description", help="Issue description."),
    assignee: str | None = typer.Option(None, "--assignee", help="Username to assign at creation."),
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
        return _require_client().request("POST", "/api/2/issue", json_body={"fields": fields})

    payload = _require_success("issue create", run)
    if raw:
        _echo_json(payload)
        return
    if isinstance(payload, dict):
        typer.echo(f"Created issue: {payload.get('key')} (id={payload.get('id')})")
    else:
        typer.echo(str(payload))


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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
