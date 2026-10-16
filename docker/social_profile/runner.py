"""Bounded social-profile lookup and offline URL parsing.

`--health` is offline and prints exactly `ok` on stdout. CrossLinked search
pages are fetched once per engine; challenges are surfaced without retry.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Any
from urllib.parse import quote, urlsplit

SUPPORTED_SUB_SOURCES = ("crosslinked", "slinky")

UNSUPPORTED_SUB_SOURCES = {
    "tiktok-hashtag-analysis": (
        "Upstream collector uses TikTokApi and Playwright, automatically retries headed after errors, "
        "and its TikTokApi dependency uses stealth/browser behavior to avoid bot detection. No bounded "
        "stable public API contract is used; no CAPTCHA or anti-bot challenge is bypassed. See "
        "https://github.com/bellingcat/tiktok-hashtag-analysis/blob/main/tiktok_hashtag_analysis/base.py "
        "and https://github.com/davidteather/TikTok-Api/blob/main/TikTokApi/tiktok.py."
    ),
    "zehef": (
        "Zehef accepts email seeds and combines account-creation endpoint checks with breach/stealer "
        "queries, outside this profile adapter's input/output scope. See "
        "https://github.com/N0rz3/Zehef/blob/master/modules/accounts/instagram.py and "
        "https://github.com/N0rz3/Zehef/blob/master/modules/breaches/hudsonrock.py."
    ),
}

USER_AGENT = "Aletheia/1.0 (+https://github.com/frostknightfrosty-lgtm/aletheia)"
SEARCH_TIMEOUT_SECONDS = 5
MAX_RECORDS = 25
SLINKY_BINARY = "/usr/local/bin/slinky-profile"


class SourceResult:
    def __init__(
        self,
        name: str,
        *,
        data: dict[str, Any] | None = None,
        error: str | None = None,
        http_status: int = 0,
        skipped: bool = False,
        skip_reason: str | None = None,
    ) -> None:
        self.name = name
        self.data = data
        self.error = error
        self.http_status = http_status
        self.skipped = skipped
        self.skip_reason = skip_reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.name,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "http_status": self.http_status,
            "error": self.error,
            "data": self.data,
        }


def _skip(name: str, reason: str) -> SourceResult:
    return SourceResult(name, skipped=True, skip_reason=reason)


def _crosslinked_class():
    from crosslinked.search import CrossLinked

    return CrossLinked


def _fetch_search_page(url: str):
    import requests

    return requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        timeout=SEARCH_TIMEOUT_SECONDS,
        allow_redirects=False,
        verify=True,
    )


def _profile_url(raw_url: str) -> tuple[str, str] | None:
    parsed = urlsplit(raw_url.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() != "https" or not host:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    if not (host == "linkedin.com" or host.endswith(".linkedin.com")):
        return None
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) < 2 or segments[0].lower() != "in":
        return None
    return f"https://{parsed.netloc}{parsed.path}", segments[1]


def _challenge_page(response: Any) -> bool:
    text = str(getattr(response, "text", "")).lower()
    return any(
        marker in text
        for marker in (
            "unusual traffic",
            "verify you are human",
            "captcha",
            "/sorry/index",
        )
    )


def query_crosslinked(company: str) -> SourceResult:
    records: list[dict[str, str]] = []
    engine_errors: list[str] = []
    last_status = 0
    crosslinked = _crosslinked_class()

    for engine in ("google", "bing"):
        parser = crosslinked(
            search_engine=engine,
            target=company,
            timeout=1,
            conn_timeout=SEARCH_TIMEOUT_SECONDS,
            proxies=[],
            jitter=0,
        )
        target = quote(company, safe="")
        search_url = parser.url[engine].format(target, 0)
        if engine == "bing":
            search_url = search_url.replace("http://www.bing.com/", "https://www.bing.com/", 1)
        try:
            response = _fetch_search_page(search_url)
        except Exception as exc:  # source-specific failure is kept partial, not retried
            engine_errors.append(f"{engine}: {type(exc).__name__}")
            continue

        last_status = int(getattr(response, "status_code", 0) or 0)
        if _challenge_page(response):
            engine_errors.append(f"{engine}: search challenge returned; stopped without retry")
            continue
        if last_status != 200:
            engine_errors.append(f"{engine}: HTTP {last_status}; stopped without redirect or retry")
            continue

        try:
            parser.page_parser(response)
        except Exception as exc:
            engine_errors.append(f"{engine}: parse error {type(exc).__name__}")
            continue
        for item in parser.results:
            parsed = _profile_url(str(item.get("url") or ""))
            name = str(item.get("name") or "").strip()
            if parsed is None or not name:
                continue
            source_url, username = parsed
            records.append(
                {
                    "name": name,
                    "username": username,
                    "company": company,
                    "source_url": source_url,
                }
            )
            if len(records) >= MAX_RECORDS:
                break
        if len(records) >= MAX_RECORDS:
            break

    deduplicated = {item["source_url"]: item for item in records}
    error = "; ".join(engine_errors) if engine_errors else None
    return SourceResult(
        "crosslinked",
        data={"records": list(deduplicated.values()), "query_count_max": 2},
        error=error,
        http_status=last_status,
    )


def query_slinky(profile_url: str) -> SourceResult:
    parsed = urlsplit(profile_url.strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        return SourceResult("slinky", error="Input must be an absolute HTTPS profile URL")
    try:
        completed = subprocess.run(
            [SLINKY_BINARY, profile_url.strip()],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return SourceResult("slinky", error=f"{type(exc).__name__}: URL parser unavailable or timed out")
    if completed.returncode != 0:
        return SourceResult("slinky", error=completed.stderr.strip() or "Unsupported profile URL")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return SourceResult("slinky", error="URL parser output was not valid JSON")
    username = str(payload.get("id") or "").strip()
    source_url = str(payload.get("url") or "").strip()
    if not username or not source_url.startswith("https://"):
        return SourceResult("slinky", error="URL parser did not return a public HTTPS user profile")
    return SourceResult("slinky", data={"records": [{"username": username, "source_url": source_url}]})


def _health_inventory() -> dict[str, Any]:
    sub_sources = [
        {"source": name, "enabled_by_default": True, "requires_key": False}
        for name in SUPPORTED_SUB_SOURCES
    ]
    sub_sources.extend(
        {
            "source": name,
            "enabled_by_default": False,
            "requires_key": False,
            "skip_reason": reason,
        }
        for name, reason in sorted(UNSUPPORTED_SUB_SOURCES.items())
    )
    return {"health": "ok", "network_used": False, "sub_sources": sub_sources}


def run(input_type: str, value: str) -> dict[str, Any]:
    if not value.strip():
        raise ValueError("Input value must not be empty")
    if input_type not in {"company_name", "url"}:
        raise ValueError("Input type must be company_name or url")

    if input_type == "company_name":
        crosslinked = query_crosslinked(value.strip())
        slinky = _skip("slinky", "Slinky applies only to an HTTPS social-profile URL")
    else:
        crosslinked = _skip("crosslinked", "CrossLinked applies only to a company-name search")
        slinky = query_slinky(value.strip())

    return {
        "input_type": input_type,
        "input_value": value.strip(),
        "sources": [
            crosslinked.to_dict(),
            slinky.to_dict(),
            *(_skip(name, reason).to_dict() for name, reason in sorted(UNSUPPORTED_SUB_SOURCES.items())),
        ],
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--health"]:
        print("ok")
        print(json.dumps(_health_inventory(), sort_keys=True), file=sys.stderr)
        return 0
    if len(args) != 2:
        print("usage: runner.py <company_name|url> <value>", file=sys.stderr)
        return 2
    try:
        payload = run(args[0], args[1])
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
