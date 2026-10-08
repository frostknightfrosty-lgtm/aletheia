import base64
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://lookups.twilio.com/v2/PhoneNumbers/"


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--health":
        print("ok")
        return 0
    if len(sys.argv) != 2:
        print("usage: runner.py <phone>", file=sys.stderr)
        return 2
    key = os.getenv("TWILIO_API_KEY")
    secret = os.getenv("TWILIO_API_SECRET")
    if not key or not secret:
        print("TWILIO_API_KEY and TWILIO_API_SECRET are required", file=sys.stderr)
        return 3
    phone = sys.argv[1].strip()
    url = BASE + urllib.parse.quote(phone, safe="+")
    token = base64.b64encode(f"{key}:{secret}".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {token}", "Accept": "application/json", "User-Agent": "Aletheia/0.4.0"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=ssl.create_default_context()) as resp:
            print(resp.read().decode("utf-8"))
        return 0
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        print(json.dumps({"http_status": exc.code, "error": detail}), file=sys.stderr)
        return 4
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
