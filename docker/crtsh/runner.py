import json
import ssl
import sys
import urllib.parse
import urllib.request


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--health":
        print("ok")
        return 0
    if len(sys.argv) != 2:
        print("usage: runner.py <domain>", file=sys.stderr)
        return 2
    domain = sys.argv[1].strip().lower().rstrip(".")
    if not domain or "/" in domain or " " in domain:
        print("invalid domain", file=sys.stderr)
        return 2
    query = urllib.parse.quote(f"%.{domain}", safe="%.")
    url = f"https://crt.sh/?q={query}&output=json"
    req = urllib.request.Request(url, headers={"User-Agent": "Aletheia/0.5.0"})
    with urllib.request.urlopen(req, timeout=60, context=ssl.create_default_context()) as resp:
        payload = json.load(resp)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
