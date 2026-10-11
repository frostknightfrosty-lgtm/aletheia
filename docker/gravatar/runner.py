from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit


BASE = "https://api.gravatar.com/v3/profiles/"
TEXT_FIELDS = ("display_name", "location", "description", "job_title", "company")
URL_FIELDS = ("profile_url", "avatar_url")


def _https(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parts = urlsplit(value)
    return parts.scheme == "https" and bool(parts.netloc)


def curate(payload: object, expected_hash: str) -> dict | None:
    """Reduce a Gravatar profile response to the reviewed public fields.

    Contact details, payments/wallets, links, galleries, verified accounts, and
    every other field are dropped here so they never leave the container.
    """
    if not isinstance(payload, dict) or payload.get("hash") != expected_hash:
        return None
    curated: dict[str, object] = {"hash": expected_hash}
    for field in TEXT_FIELDS:
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            curated[field] = value
    for field in URL_FIELDS:
        if _https(payload.get(field)):
            curated[field] = payload[field]
    if payload.get("is_organization") is True:
        curated["is_organization"] = True
    return curated


def main() -> int:
    if sys.argv[1:] == ["--health"]:
        print("ok")
        return 0
    if len(sys.argv) != 3 or sys.argv[1] != "hash" or not re.fullmatch(r"[0-9a-f]{64}", sys.argv[2]):
        print("usage: runner.py hash <email-sha256>", file=sys.stderr)
        return 2

    profile_hash = sys.argv[2]
    headers = {"Accept": "application/json", "User-Agent": "Aletheia/0.7.0"}
    api_key = os.environ.get("GRAVATAR_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(BASE + profile_hash, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read(1_000_001)
        if len(body) > 1_000_000:
            print("Gravatar response exceeded the 1 MB safety limit", file=sys.stderr)
            return 4
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            print("Gravatar response was not valid JSON", file=sys.stderr)
            return 4
        curated = curate(payload, profile_hash)
        if curated is None:
            print("Gravatar response did not match the requested profile hash", file=sys.stderr)
            return 4
        print(json.dumps(curated, ensure_ascii=False, sort_keys=True))
        return 0
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print(json.dumps({"http_status": 404, "status": "not_found"}))
            return 0
        print(json.dumps({"http_status": exc.code, "error": "Gravatar request failed"}), file=sys.stderr)
        return 4
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"Gravatar request failed: {type(exc).__name__}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
