import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://haveibeenpwned.com/api/v3"
UA = "Aletheia/0.4.0"


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--health":
        print("ok")
        return 0
    if len(sys.argv) != 3 or sys.argv[1] != "email":
        print("usage: runner.py email <address>", file=sys.stderr)
        return 2
    key = os.getenv("HIBP_API_KEY")
    if not key:
        print("HIBP_API_KEY is required", file=sys.stderr)
        return 3
    email = sys.argv[2].strip()
    if not email or "@" not in email:
        print("invalid email", file=sys.stderr)
        return 2
    url = f"{BASE}/breachedaccount/{urllib.parse.quote(email, safe='')}?truncateResponse=false"
    req = urllib.request.Request(url, headers={"hibp-api-key": key, "user-agent": UA, "accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=ssl.create_default_context()) as resp:
            print(resp.read().decode("utf-8"))
        return 0
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        if exc.code == 404:
            print("[]")
            return 0
        print(json.dumps({"http_status": exc.code, "error": body}), file=sys.stderr)
        return 4
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
