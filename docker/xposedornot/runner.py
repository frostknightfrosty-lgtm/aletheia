from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.xposedornot.com/v1/check-email/"


def main() -> int:
    if sys.argv[1:] == ["--health"]:
        print("ok")
        return 0
    if len(sys.argv) != 3 or sys.argv[1] != "email":
        print("usage: runner.py email <address>", file=sys.stderr)
        return 2

    email = sys.argv[2].strip()
    if email.count("@") != 1 or email.startswith("@") or email.endswith("@") or any(ch.isspace() for ch in email):
        print("invalid email", file=sys.stderr)
        return 2

    url = BASE + urllib.parse.quote(email, safe="")
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Aletheia/0.7.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print(response.read().decode("utf-8"))
        return 0
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print(exc.read().decode("utf-8", "replace"))
            return 0
        print(json.dumps({"http_status": exc.code, "error": "XposedOrNot request failed"}), file=sys.stderr)
        return 4
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"XposedOrNot network request failed: {type(exc).__name__}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
