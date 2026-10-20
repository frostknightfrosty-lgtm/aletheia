"""Bounded public GitHub identity expansion driver.

Five public REST reads plus the public ``.keys`` text endpoint turn one
username into a normalized JSON document. No token, account, or login is used.
The unauthenticated REST limit is 60 requests/hour per source IP; the runner
makes six requests per invocation, records the returned rate-limit headers, and
never retries.

Only public, account-scoped metadata is emitted. The profile ``email`` field is
deliberately dropped, and SSH keys are reduced to their OpenSSH SHA-256
fingerprint instead of storing the key material.

``--health`` and ``--selftest`` are offline. ``--normalize`` re-validates a saved
combined document and is the case run under ``--network none``.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REVIEWED_ON = "2026-10-20"
API_ROOT = "https://api.github.com"
KEYS_ROOT = "https://github.com"
API_VERSION = "2022-11-28"
USER_AGENT = (
    "Aletheia/0.1 (https://github.com/frostknightfrosty-lgtm/aletheia; "
    "public GitHub metadata lookup)"
)
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
HTTP_TIMEOUT_SECONDS = 30
MAX_REPOS = 5
MAX_GISTS = 5
MAX_EVENTS = 5
MAX_KEYS = 10
MAX_TOPICS = 10
MAX_ERRORS = 10
USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
FINGERPRINT_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")


def _text(value: Any, limit: int = 300) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _read_username(path: Path) -> str:
    if not path.exists() or not path.is_file():
        raise ValueError(f"username file not found: {path}")
    data = path.read_bytes()
    if len(data) > 128:
        raise ValueError("username file exceeds 128 bytes")
    value = data.decode("utf-8", errors="strict").strip()
    if "\n" in value or "\r" in value:
        raise ValueError("username file must contain exactly one line")
    if not USERNAME_RE.fullmatch(value):
        raise ValueError("invalid GitHub username")
    return value


def _api_url(path: str) -> str:
    return f"{API_ROOT}{path}"


def _headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
    }


def _rate_limit(headers: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for source, target in (
        ("X-RateLimit-Limit", "limit"),
        ("X-RateLimit-Remaining", "remaining"),
        ("X-RateLimit-Used", "used"),
        ("X-RateLimit-Reset", "reset"),
        ("X-RateLimit-Resource", "resource"),
    ):
        try:
            raw = headers.get(source) if headers is not None else None
        except Exception:  # noqa: BLE001
            raw = None
        if raw is None:
            continue
        if target == "resource":
            text = _text(str(raw), 64)
            if text:
                values[target] = text
        else:
            try:
                values[target] = int(str(raw))
            except ValueError:
                continue
    if isinstance(values.get("reset"), int):
        try:
            values["reset_at"] = datetime.fromtimestamp(
                values["reset"], timezone.utc
            ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError):
            pass
    return values


def _fetch_json(url: str, *, allow_404: bool = False) -> tuple[Any, int, dict[str, Any], str | None]:
    request = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            status = response.status
            rate = _rate_limit(response.headers)
            if len(body) > MAX_RESPONSE_BYTES:
                return None, status, rate, "response exceeded the 4 MB safety limit"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        if allow_404 and exc.code == 404:
            return None, 404, _rate_limit(exc.headers), None
        return None, exc.code, _rate_limit(exc.headers), f"HTTP {exc.code}: {detail[:500]}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, 0, {}, f"{type(exc).__name__}: {exc}"
    try:
        return json.loads(body.decode("utf-8", errors="replace")), status, rate, None
    except json.JSONDecodeError as exc:
        return None, status, rate, f"JSON decode error: {exc}"


def _fetch_text(url: str) -> tuple[str | None, int, str | None]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            status = response.status
            if len(body) > MAX_RESPONSE_BYTES:
                return None, status, "response exceeded the 4 MB safety limit"
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return "", 404, None
        return None, exc.code, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, 0, f"{type(exc).__name__}: {exc}"
    return body.decode("utf-8", errors="replace"), status, None


def _fingerprint(key_line: Any) -> tuple[str, str] | None:
    text = _text(key_line, 2000)
    if not text:
        return None
    parts = text.split()
    if len(parts) < 2:
        return None
    key_type, blob = parts[0], parts[1]
    if not key_type.startswith(("ssh-", "ecdsa-")) or len(blob) > 1500:
        return None
    try:
        decoded = base64.b64decode(blob, validate=True)
    except (ValueError, TypeError):
        return None
    if not decoded:
        return None
    digest = base64.b64encode(hashlib.sha256(decoded).digest()).decode("ascii").rstrip("=")
    return key_type[:32], f"SHA256:{digest}"


def _keys_from_api(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    out: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        parsed = _fingerprint(item.get("key"))
        if parsed is None:
            continue
        key_type, fingerprint = parsed
        out.append({
            "fingerprint": fingerprint,
            "key_type": key_type,
            "source": "api",
        })
    return _unique_keys(out)


def _keys_from_text(text: Any) -> list[dict[str, Any]]:
    if not isinstance(text, str):
        return []
    out: list[dict[str, Any]] = []
    for line in text.splitlines()[:MAX_KEYS * 2]:
        parsed = _fingerprint(line)
        if parsed is None:
            continue
        key_type, fingerprint = parsed
        out.append({
            "fingerprint": fingerprint,
            "key_type": key_type,
            "source": "dotkeys",
        })
    return _unique_keys(out)


def _unique_keys(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in values:
        fingerprint = item.get("fingerprint")
        if not isinstance(fingerprint, str) or fingerprint in seen:
            continue
        if not FINGERPRINT_RE.fullmatch(fingerprint):
            continue
        seen.add(fingerprint)
        out.append(item)
        if len(out) >= MAX_KEYS:
            break
    return out


def _clean_profile(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    login = _text(payload.get("login"), 64)
    if not login:
        return None
    return {
        "login": login,
        "name": _text(payload.get("name"), 200),
        "company": _text(payload.get("company"), 200),
        "blog": _text(payload.get("blog"), 300),
        "location": _text(payload.get("location"), 200),
        "bio": _text(payload.get("bio"), 500),
        "twitter_username": _text(payload.get("twitter_username"), 120),
        "public_repos": _number(payload.get("public_repos")),
        "public_gists": _number(payload.get("public_gists")),
        "followers": _number(payload.get("followers")),
        "following": _number(payload.get("following")),
        "created_at": _text(payload.get("created_at"), 64),
        "updated_at": _text(payload.get("updated_at"), 64),
        "html_url": _text(payload.get("html_url"), 300),
    }


def _clean_repos(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    out: list[dict[str, Any]] = []
    for item in payload[:MAX_REPOS]:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"), 200)
        if not name:
            continue
        topics = item.get("topics") if isinstance(item.get("topics"), list) else []
        out.append({
            "name": name,
            "html_url": _text(item.get("html_url"), 300),
            "description": _text(item.get("description"), 500),
            "language": _text(item.get("language"), 80),
            "topics": [_text(value, 80) for value in topics[:MAX_TOPICS]
                       if _text(value, 80)],
            "fork": _bool(item.get("fork")),
            "archived": _bool(item.get("archived")),
            "stargazers_count": _number(item.get("stargazers_count")),
            "created_at": _text(item.get("created_at"), 64),
            "updated_at": _text(item.get("updated_at"), 64),
        })
    return out


def _clean_gists(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    out: list[dict[str, Any]] = []
    for item in payload[:MAX_GISTS]:
        if not isinstance(item, dict):
            continue
        gist_id = _text(item.get("id"), 64)
        if not gist_id:
            continue
        files = item.get("files")
        out.append({
            "id": gist_id,
            "html_url": _text(item.get("html_url"), 300),
            "description": _text(item.get("description"), 300),
            "public": _bool(item.get("public")),
            "file_count": len(files) if isinstance(files, dict) else None,
            "created_at": _text(item.get("created_at"), 64),
            "updated_at": _text(item.get("updated_at"), 64),
        })
    return out


def _clean_events(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    out: list[dict[str, Any]] = []
    for item in payload[:MAX_EVENTS]:
        if not isinstance(item, dict):
            continue
        event_type = _text(item.get("type"), 80)
        if not event_type:
            continue
        repo = item.get("repo") if isinstance(item.get("repo"), dict) else {}
        out.append({
            "id": _text(item.get("id"), 64),
            "type": event_type,
            "repo_name": _text(repo.get("name"), 200),
            "created_at": _text(item.get("created_at"), 64),
        })
    return out


def _collect(username: str) -> dict[str, Any]:
    collected: dict[str, Any] = {
        "source": "github_identity",
        "status": "ok",
        "username": username,
        "profile": None,
        "repos": [],
        "gists": [],
        "events": [],
        "ssh_keys": [],
        "rate_limit": {},
        "errors": [],
    }
    profile, status, rate, error = _fetch_json(_api_url(f"/users/{username}"))
    if rate:
        collected["rate_limit"] = rate
    if error:
        collected["errors"].append(f"profile: {error}")
        collected["status"] = "error"
        return collected
    collected["profile"] = _clean_profile(profile)
    if collected["profile"] is None:
        collected["errors"].append("profile: response was not a GitHub user object")
        collected["status"] = "error"
        return collected

    endpoints = (
        ("repos", f"/users/{username}/repos?per_page={MAX_REPOS}&sort=updated", _clean_repos),
        ("gists", f"/users/{username}/gists?per_page={MAX_GISTS}", _clean_gists),
        ("events", f"/users/{username}/events/public?per_page={MAX_EVENTS}", _clean_events),
    )
    for key, path, cleaner in endpoints:
        payload, status, rate, error = _fetch_json(_api_url(path))
        if rate:
            collected["rate_limit"] = rate
        if error:
            collected["errors"].append(f"{key}: {error}")
            continue
        collected[key] = cleaner(payload)

    payload, status, rate, error = _fetch_json(
        _api_url(f"/users/{username}/keys"), allow_404=True
    )
    if rate:
        collected["rate_limit"] = rate
    if error:
        collected["errors"].append(f"ssh_keys: {error}")
    elif payload is None and status == 404:
        pass
    else:
        collected["ssh_keys"] = _keys_from_api(payload)

    text, status, error = _fetch_text(f"{KEYS_ROOT}/{username}.keys")
    if error:
        collected["errors"].append(f"dotkeys: {error}")
    elif text:
        collected["ssh_keys"] = _unique_keys(
            collected["ssh_keys"] + _keys_from_text(text)
        )

    if collected["errors"]:
        collected["status"] = "partial"
    return collected


def _normalise(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("document must be a JSON object")
    if raw.get("source") != "github_identity":
        raise ValueError("document source must be 'github_identity'")
    username = _text(raw.get("username"), 64)
    if not username or not USERNAME_RE.fullmatch(username):
        raise ValueError("document username is invalid")
    status = _text(raw.get("status"), 32) or "ok"
    if status not in {"ok", "partial", "error", "invalid_target"}:
        raise ValueError(f"unsupported document status: {status}")

    errors: list[str] = []
    raw_errors = raw.get("errors") if isinstance(raw.get("errors"), list) else []
    for item in raw_errors:
        value = _text(item, 300)
        if value:
            errors.append(value)
        if len(errors) >= MAX_ERRORS:
            break

    profile = _clean_profile(raw.get("profile"))
    repos = _clean_repos(raw.get("repos"))
    gists = _clean_gists(raw.get("gists"))
    events = _clean_events(raw.get("events"))

    raw_keys = raw.get("ssh_keys") if isinstance(raw.get("ssh_keys"), list) else []
    keys: list[dict[str, Any]] = []
    for item in raw_keys:
        if not isinstance(item, dict):
            continue
        fingerprint = _text(item.get("fingerprint"), 100)
        key_type = _text(item.get("key_type"), 32)
        source = _text(item.get("source"), 16)
        if not fingerprint or not FINGERPRINT_RE.fullmatch(fingerprint):
            continue
        if not key_type or source not in {"api", "dotkeys"}:
            continue
        keys.append({"fingerprint": fingerprint, "key_type": key_type,
                     "source": source})
    keys = _unique_keys(keys)

    rate = raw.get("rate_limit") if isinstance(raw.get("rate_limit"), dict) else {}
    rate_limit: dict[str, Any] = {}
    for key in ("limit", "remaining", "used", "reset"):
        number = _number(rate.get(key))
        if number is not None:
            rate_limit[key] = int(number)
    for key in ("resource", "reset_at"):
        value = _text(rate.get(key), 64)
        if value:
            rate_limit[key] = value

    if status == "ok" and errors:
        status = "partial"
    return {
        "source": "github_identity",
        "status": status,
        "username": username,
        "profile": profile,
        "repos": repos,
        "gists": gists,
        "events": events,
        "ssh_keys": keys,
        "rate_limit": rate_limit,
        "errors": errors,
    }


_SAMPLE_KEY = "ssh-ed25519 " + base64.b64encode(b"aletheia-synthetic-key").decode()
_SAMPLE_PROFILE = {
    "login": "octo-example",
    "name": "Octo Example",
    "email": "private@example.org",
    "company": "Example Org",
    "blog": "https://example.org",
    "location": "Example City",
    "bio": "Synthetic profile",
    "twitter_username": "octo_example",
    "public_repos": 3,
    "public_gists": 1,
    "followers": 2,
    "following": 4,
    "created_at": "2020-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
    "html_url": "https://github.com/octo-example",
}
_SAMPLE_REPOS = [{
    "name": "example-repo",
    "html_url": "https://github.com/octo-example/example-repo",
    "description": "Synthetic repository",
    "language": "Python",
    "topics": ["osint", "synthetic"],
    "fork": False,
    "archived": False,
    "stargazers_count": 1,
    "created_at": "2021-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}]
_SAMPLE_GISTS = [{
    "id": "abc123",
    "html_url": "https://gist.github.com/octo-example/abc123",
    "description": "Synthetic gist",
    "public": True,
    "files": {"example.txt": {}},
    "created_at": "2022-01-01T00:00:00Z",
    "updated_at": "2022-01-01T00:00:00Z",
}]
_SAMPLE_EVENTS = [{
    "id": "123",
    "type": "PushEvent",
    "repo": {"name": "octo-example/example-repo"},
    "created_at": "2026-01-01T00:00:00Z",
    "payload": {"commits": []},
}]
_SAMPLE_KEYS = [{"id": 1, "key": _SAMPLE_KEY,
                 "created_at": "2020-01-01T00:00:00Z",
                 "last_used": "2026-01-01T00:00:00Z"}]


def _health() -> int:
    payload = {
        "source": "github_identity",
        "reviewed_on": REVIEWED_ON,
        "api_version": API_VERSION,
        "endpoints": [
            "https://api.github.com/users/{username}",
            "https://api.github.com/users/{username}/repos",
            "https://api.github.com/users/{username}/gists",
            "https://api.github.com/users/{username}/events/public",
            "https://api.github.com/users/{username}/keys",
            "https://github.com/{username}.keys",
        ],
        "network_required": True,
        "credentials_required": False,
        "unauthenticated_rest_limit": "60 requests/hour per source IP",
        "requests_per_run": 6,
        "max_repos": MAX_REPOS,
        "max_gists": MAX_GISTS,
        "max_events": MAX_EVENTS,
        "max_ssh_keys": MAX_KEYS,
    }
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)
    print("ok")
    return 0


def _selftest() -> int:
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    try:
        check("username_validation",
              bool(USERNAME_RE.fullmatch("octo-example"))
              and not USERNAME_RE.fullmatch("-bad")
              and not USERNAME_RE.fullmatch("bad-")
              and not USERNAME_RE.fullmatch("bad--name"),
              "GitHub username grammar")
    except Exception as exc:  # noqa: BLE001
        check("username_validation", False, str(exc)[:200])
    try:
        parsed = _fingerprint(_SAMPLE_KEY)
        check("ssh_fingerprint", parsed is not None
              and parsed[1].startswith("SHA256:")
              and len(parsed[1]) == 50,
              "OpenSSH SHA-256 fingerprint")
    except Exception as exc:  # noqa: BLE001
        check("ssh_fingerprint", False, str(exc)[:200])
    try:
        combined = {
            "source": "github_identity",
            "status": "ok",
            "username": "octo-example",
            "profile": _SAMPLE_PROFILE,
            "repos": _SAMPLE_REPOS,
            "gists": _SAMPLE_GISTS,
            "events": _SAMPLE_EVENTS,
            "ssh_keys": _keys_from_api(_SAMPLE_KEYS),
            "rate_limit": {"limit": 60, "remaining": 54, "used": 6, "reset": 1},
            "errors": [],
        }
        normalized = _normalise(combined)
        check("profile_email_excluded",
              "email" not in normalized["profile"]
              and "private@example.org" not in json.dumps(normalized),
              "profile email omitted")
        check("combined_normalisation",
              normalized["profile"]["login"] == "octo-example"
              and len(normalized["repos"]) == 1
              and len(normalized["gists"]) == 1
              and len(normalized["events"]) == 1
              and len(normalized["ssh_keys"]) == 1,
              "synthetic combined document")
    except Exception as exc:  # noqa: BLE001
        check("profile_email_excluded", False, str(exc)[:200])
        check("combined_normalisation", False, str(exc)[:200])
    try:
        dots = _keys_from_text((_SAMPLE_KEY + "\n" + _SAMPLE_KEY + "\n"))
        check("dotkeys_dedupe", len(dots) == 1 and dots[0]["source"] == "dotkeys",
              "duplicate line removed")
    except Exception as exc:  # noqa: BLE001
        check("dotkeys_dedupe", False, str(exc)[:200])
    try:
        bounded = _normalise({
            "source": "github_identity", "status": "ok", "username": "octo-example",
            "profile": _SAMPLE_PROFILE,
            "repos": _SAMPLE_REPOS * 20, "gists": _SAMPLE_GISTS * 20,
            "events": _SAMPLE_EVENTS * 20, "ssh_keys": _keys_from_api(_SAMPLE_KEYS) * 20,
            "errors": ["x"] * 20,
        })
        check("bounds", len(bounded["repos"]) == MAX_REPOS
              and len(bounded["gists"]) == MAX_GISTS
              and len(bounded["events"]) == MAX_EVENTS
              and len(bounded["ssh_keys"]) == 1
              and len(bounded["errors"]) == MAX_ERRORS,
              f"max {MAX_REPOS}/{MAX_GISTS}/{MAX_EVENTS}, max {MAX_KEYS} keys")
    except Exception as exc:  # noqa: BLE001
        check("bounds", False, str(exc)[:200])
    try:
        _normalise({"source": "github_identity", "username": "bad name"})
        check("invalid_document", False, "accepted invalid username")
    except ValueError:
        check("invalid_document", True, "rejected invalid username")
    check("endpoint_policy",
          API_VERSION == "2022-11-28" and API_ROOT.startswith("https://")
          and KEYS_ROOT.startswith("https://"),
          f"API {API_VERSION}")
    check("no_credentials", True, "unauthenticated public endpoints only")
    print(json.dumps({
        "github_identity_selftest": "ok" if all(c["ok"] for c in checks) else "failed",
        "reviewed_on": REVIEWED_ON,
        "checks": checks,
    }, sort_keys=True, indent=2))
    return 0 if all(item["ok"] for item in checks) else 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--health", action="store_true")
    group.add_argument("--selftest", action="store_true")
    group.add_argument("--normalize", metavar="COMBINED_JSON")
    parser.add_argument("username_file", nargs="?")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.health:
        return _health()
    if args.selftest:
        return _selftest()
    if args.normalize:
        try:
            raw = json.loads(Path(args.normalize).read_text(encoding="utf-8"))
            print(json.dumps(_normalise(raw), sort_keys=True, indent=2))
            return 0
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"source": "github_identity",
                              "status": "invalid_document",
                              "error": str(exc)[:300]}, sort_keys=True))
            return 2
    if not args.username_file:
        print(json.dumps({"source": "github_identity", "status": "invalid_target",
                          "error": "one GitHub username file is required"},
                         sort_keys=True))
        return 2
    try:
        username = _read_username(Path(args.username_file))
    except ValueError as exc:
        print(json.dumps({"source": "github_identity", "status": "invalid_target",
                          "error": str(exc)}, sort_keys=True))
        return 2
    result = _normalise(_collect(username))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["status"] in {"ok", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
