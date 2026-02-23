from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "jiradc-cli" / "config.json"


class ConfigError(RuntimeError):
    """Raised when the local CLI configuration is missing or invalid."""


@dataclass(slots=True)
class JiraConfig:
    base_url: str
    cookie: str


def normalize_base_url(base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    if not value.startswith("http://") and not value.startswith("https://"):
        raise ConfigError("Base URL must start with http:// or https://")
    return value


def normalize_cookie(cookie: str) -> str:
    value = cookie.strip()
    if value.lower().startswith("cookie:"):
        value = value.split(":", 1)[1].strip()
    if not value:
        raise ConfigError("Cookie value cannot be empty.")
    if "=" not in value:
        value = f"JSESSIONID={value}"
    return value


def parse_cookie_pairs(cookie: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    normalized = normalize_cookie(cookie)
    for part in normalized.split(";"):
        chunk = part.strip()
        if not chunk or "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            pairs[key] = value
    return pairs


def format_cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{key}={value}" for key, value in cookies.items())


def pick_session_cookies(cookie: str) -> str:
    """Keep cookies most likely required for Jira session/auth routing."""
    all_pairs = parse_cookie_pairs(cookie)
    if not all_pairs:
        raise ConfigError("Cookie value does not contain valid key=value pairs.")

    preferred_names: list[str] = [
        "JSESSIONID",
        "atlassian.xsrf.token",
        "seraph.rememberme.cookie",
        "AWSALB",
        "AWSALBCORS",
        "ROUTEID",
        "GCP_IAP_UID",
        "BIGipServer",
    ]

    selected: dict[str, str] = {}
    for name in preferred_names:
        if name in all_pairs:
            selected[name] = all_pairs[name]

    for name, value in all_pairs.items():
        lowered = name.lower()
        if lowered.startswith("atlassian.") or lowered.startswith("seraph."):
            selected.setdefault(name, value)
        if "oauth" in lowered and "proxy" in lowered:
            selected.setdefault(name, value)

    if "JSESSIONID" not in selected and "JSESSIONID" in all_pairs:
        selected["JSESSIONID"] = all_pairs["JSESSIONID"]

    if selected:
        return format_cookie_header(selected)
    return normalize_cookie(cookie)


def cookie_variants_for_auth(cookie: str) -> Iterable[str]:
    normalized = normalize_cookie(cookie)
    minimized = pick_session_cookies(normalized)
    if minimized != normalized:
        return [minimized, normalized]
    return [normalized]


def save_config(config: JiraConfig, path: Path = DEFAULT_CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass

    payload = {"base_url": normalize_base_url(config.base_url), "cookie": normalize_cookie(config.cookie)}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> JiraConfig:
    if not path.exists():
        raise ConfigError(f"Config file not found at {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config file is not valid JSON: {path}") from exc

    base_url = data.get("base_url")
    cookie = data.get("cookie")
    if not isinstance(base_url, str) or not isinstance(cookie, str):
        raise ConfigError("Config file must contain string values for 'base_url' and 'cookie'.")
    return JiraConfig(base_url=normalize_base_url(base_url), cookie=normalize_cookie(cookie))


def clear_config(path: Path = DEFAULT_CONFIG_PATH) -> bool:
    if not path.exists():
        return False
    path.unlink()
    return True
