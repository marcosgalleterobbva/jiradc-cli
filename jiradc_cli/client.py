from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import requests

from .config import JiraConfig


@dataclass(slots=True)
class JiraApiError(RuntimeError):
    status_code: int
    message: str

    def __str__(self) -> str:
        return f"HTTP {self.status_code}: {self.message}"


@dataclass(slots=True)
class JiraTransportError(RuntimeError):
    message: str

    def __str__(self) -> str:
        return self.message


class JiraClient:
    def __init__(self, config: JiraConfig, timeout_seconds: int = 30) -> None:
        self.base_url = config.base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.xsrf_token = _extract_xsrf_token(config.cookie)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Cookie": config.cookie,
                "X-Requested-With": "XMLHttpRequest",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            }
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | list[Any] | None = None,
        data: dict[str, Any] | None = None,
        files: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        url = f"{self.base_url}/rest{path}"
        method_upper = method.upper()
        request_headers = dict(self.session.headers)
        if method_upper in {"POST", "PUT", "PATCH", "DELETE"}:
            # Jira Data Center instances behind SSO/WAF frequently enforce XSRF checks on mutations.
            if self.xsrf_token:
                request_headers["X-Atlassian-Token"] = self.xsrf_token
            else:
                request_headers.setdefault("X-Atlassian-Token", "no-check")
            request_headers.setdefault("Origin", self.base_url)
            request_headers.setdefault(
                "Referer", f"{self.base_url}/secure/Dashboard.jspa"
            )
        if headers:
            request_headers.update(headers)
        try:
            response = self.session.request(
                method=method_upper,
                url=url,
                params=params,
                json=json_body,
                data=data,
                files=files,
                headers=request_headers,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise JiraTransportError(str(exc)) from exc
        if response.status_code >= 400:
            raise JiraApiError(response.status_code, _error_message(response))
        if response.status_code == 204 or not response.text.strip():
            return None
        try:
            return response.json()
        except ValueError:
            return response.text


def _error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        if _looks_like_html(text):
            return _summarize_html_error(text, response.status_code)
        return text or response.reason

    if isinstance(payload, dict):
        errors = []
        if isinstance(payload.get("errorMessages"), list):
            errors.extend(str(item) for item in payload["errorMessages"])
        if isinstance(payload.get("errors"), dict):
            errors.extend(f"{key}: {value}" for key, value in payload["errors"].items())
        if errors:
            return "; ".join(errors)
    return str(payload)


def _looks_like_html(text: str) -> bool:
    lowered = text.lstrip().lower()
    return lowered.startswith("<!doctype html") or lowered.startswith("<html")


def _extract_xsrf_token(cookie: str) -> str | None:
    for part in cookie.split(";"):
        chunk = part.strip()
        if chunk.lower().startswith("atlassian.xsrf.token="):
            return chunk.split("=", 1)[1].strip() or None
    return None


def _summarize_html_error(text: str, status_code: int) -> str:
    referral_match = re.search(r"log-referral-id\">([^<]+)<", text, re.IGNORECASE)
    referral = referral_match.group(1).strip() if referral_match else None
    title_match = re.search(r"<title>([^<]+)</title>", text, re.IGNORECASE)
    title = title_match.group(1).strip() if title_match else "HTML error page"

    if referral:
        return f"{title} (HTTP {status_code}, referral id: {referral})"
    return f"{title} (HTTP {status_code})"
