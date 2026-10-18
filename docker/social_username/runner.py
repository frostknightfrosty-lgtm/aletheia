"""Bounded, keyless public Mastodon and GitHub username lookups."""

from __future__ import annotations

import importlib.metadata
import json
import re
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MASTO_SEARCH_URL = "https://mastodon.social/api/v2/search"
MASTODON_DOCS = "https://docs.joinmastodon.org/methods/search/"
OCTOSUITE_USER_URL = "https://api.github.com/users/{}"
OCTOSUITE_DOCS = "https://docs.github.com/en/rest/users/users#get-a-user"
USER_AGENT = "Aletheia-social-username/1.0 (+https://github.com/frostknightfrosty-lgtm/aletheia)"
HTTP_TIMEOUT_SECONDS = 5
MAX_RESPONSE_BYTES = 1_000_000

SUPPORTED_SUB_SOURCES = ("masto", "octosuite")
UNSUPPORTED_SUB_SOURCES = {
    "owasp-socialosintlm": "Requires external platform and LLM credentials; see docker/social_username/RATE_LIMITS.md.",
    "scrawler": "GUI/cookie workflow with no bounded CLI; see docker/social_username/RATE_LIMITS.md.",
}
GITHUB_LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\Z")
MASTO_USERNAME = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")


class SourceResult:
    def __init__(
        self,
        name: str,
        *,
        data: dict | None = None,
        http_status: int = 0,
        error: str | None = None,
        skipped: bool = False,
        skip_reason: str | None = None,
    ) -> None:
        self.name = name
        self.data = data
        self.http_status = http_status
        self.error = error
        self.skipped = skipped
        self.skip_reason = skip_reason
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "source": self.name,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "timestamp": self.timestamp,
            "http_status": self.http_status,
            "error": self.error,
            "data": self.data,
        }


def _skip(name: str, reason: str) -> SourceResult:
    return SourceResult(name, skipped=True, skip_reason=reason)


def _username_for_source(value: str, *, source: str) -> str | None:
    normalized = value.strip()
    if normalized.startswith("@"):
        normalized = normalized[1:]
    if source == "masto" and "@" in normalized:
        parts = normalized.split("@")
        if len(parts) != 2 or parts[1].casefold() != "mastodon.social":
            return None
        normalized = parts[0]
    elif "@" in normalized:
        return None
    if source == "masto":
        return normalized if MASTO_USERNAME.fullmatch(normalized) else None
    return normalized if GITHUB_LOGIN.fullmatch(normalized) else None


def _request_json(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[dict | list | None, int, str | None]:
    parsed = urlsplit(url)
    full_url = urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(params) if params else parsed.query, "")
    )
    request = Request(full_url, headers=headers or {})
    # ProxyHandler() reads HTTP_PROXY/HTTPS_PROXY/ALL_PROXY from the environment:
    # the container has no route out except the egress proxy, and the previous
    # empty proxy map made every request resolve hosts on the internal network
    # instead of using the proxy (live run 39125383530: EAI_AGAIN, zero proxy
    # log entries).
    opener = build_opener(ProxyHandler(), _NoRedirectHandler())
    try:
        with opener.open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            status = int(response.status)
            if status != 200:
                return None, status, f"HTTP {status}; stopped without redirect or retry"
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                return None, status, f"Response exceeded {MAX_RESPONSE_BYTES} bytes"
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return None, status, f"Invalid JSON response: {type(exc).__name__}"
        if not isinstance(value, (dict, list)):
            return None, status, "JSON response was not an object or list"
        return value, status, None
    except HTTPError as exc:
        status = int(exc.code)
        exc.close()
        if status == 404 and parsed.hostname == "api.github.com":
            return None, status, None
        return None, status, f"HTTP {status}; stopped without redirect or retry"
    except (URLError, TimeoutError, OSError) as exc:
        return None, 0, f"{type(exc).__name__}: {exc}"


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def query_masto(value: str) -> SourceResult:
    username = _username_for_source(value, source="masto")
    if username is None:
        return _skip("masto", "Input must be a username or username@mastodon.social; no other instance is contacted")
    payload, status, error = _request_json(
        MASTO_SEARCH_URL,
        params={"q": username, "type": "accounts", "limit": "5"},
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    if error:
        return SourceResult("masto", data={"records": []}, http_status=status, error=error)
    accounts = payload.get("accounts", []) if isinstance(payload, dict) else []
    records = []
    if isinstance(accounts, list):
        for account in accounts:
            if not isinstance(account, dict):
                continue
            # The directory preference is mandatory here: missing/false is treated as not discoverable.
            if account.get("discoverable") is not True:
                continue
            found_username = str(account.get("username") or "").strip()
            profile_url = account.get("url")
            if found_username.casefold() != username.casefold() or not isinstance(profile_url, str):
                continue
            if not profile_url.startswith("https://"):
                continue
            record = {
                "username": found_username,
                "profile_url": profile_url,
                "discoverable": True,
            }
            if account.get("display_name"):
                record["display_name"] = str(account["display_name"]).strip()
            records.append(record)
    return SourceResult("masto", data={"records": records}, http_status=status)


def query_octosuite(value: str) -> SourceResult:
    username = _username_for_source(value, source="octosuite")
    if username is None:
        return _skip("octosuite", "Input is not a GitHub username; no GitHub request was made")
    payload, status, error = _request_json(
        OCTOSUITE_USER_URL.format(username),
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    if status == 404 and error:
        return SourceResult("octosuite", data={"records": []}, http_status=status)
    if error:
        return SourceResult("octosuite", data={"records": []}, http_status=status, error=error)
    if not isinstance(payload, dict):
        return SourceResult("octosuite", data={"records": []}, http_status=status, error="GitHub response was not an object")
    login = str(payload.get("login") or "").strip()
    profile_url = payload.get("html_url")
    if login.casefold() != username.casefold() or not isinstance(profile_url, str):
        return SourceResult("octosuite", data={"records": []}, http_status=status)
    if not profile_url.startswith("https://github.com/"):
        return SourceResult("octosuite", data={"records": []}, http_status=status, error="GitHub returned a non-canonical profile URL")
    record = {"username": login, "profile_url": profile_url}
    if payload.get("name"):
        record["display_name"] = str(payload["name"]).strip()
    return SourceResult("octosuite", data={"records": [record]}, http_status=status)


def run(value: str) -> dict:
    return {
        "sources": [
            query_masto(value).to_dict(),
            query_octosuite(value).to_dict(),
            *[
                _skip(name, reason).to_dict()
                for name, reason in UNSUPPORTED_SUB_SOURCES.items()
            ],
        ]
    }


def _health_inventory() -> dict:
    return {
        "network_used": False,
        "sub_sources": [
            {"source": "masto", "endpoint": MASTO_SEARCH_URL, "enabled_by_default": True},
            {"source": "octosuite", "endpoint": "https://api.github.com/users/{username}", "enabled_by_default": True},
            *[
                {"source": name, "enabled_by_default": False, "skip_reason": reason}
                for name, reason in UNSUPPORTED_SUB_SOURCES.items()
            ],
        ],
        "octosuite_version": importlib.metadata.version("octosuite"),
        "masto_endpoint_docs": MASTODON_DOCS,
        "octosuite_endpoint_docs": OCTOSUITE_DOCS,
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--health"]:
        print("ok")
        print(json.dumps(_health_inventory(), sort_keys=True), file=sys.stderr)
        return 0
    if len(args) != 2 or args[0] != "username":
        print("usage: runner.py username <username>", file=sys.stderr)
        return 2
    value = args[1].strip()
    if not value:
        print(json.dumps({"error": "username must not be empty"}))
        return 2
    print(json.dumps(run(value), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
