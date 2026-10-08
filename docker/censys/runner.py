import json
import os
import ssl
import sys
import urllib.error
import urllib.request

BASE = "https://api.platform.censys.io/v3/global"


def request_json(method: str, path: str, body: dict | None = None) -> object:
    token = os.getenv("CENSYS_API_TOKEN")
    if not token:
        raise RuntimeError("CENSYS_API_TOKEN is required")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.censys.api.v3.host.v1+json",
        "Content-Type": "application/json",
        "User-Agent": "Aletheia/0.5.0",
    }
    org_id = os.getenv("CENSYS_ORG_ID")
    if org_id:
        headers["X-Organization-ID"] = org_id
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60, context=ssl.create_default_context()) as resp:
        return json.load(resp)


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--health":
        print("ok")
        return 0
    if len(sys.argv) != 3:
        print("usage: runner.py <domain|ip> <value>", file=sys.stderr)
        return 2
    kind, value = sys.argv[1], sys.argv[2]
    try:
        if kind == "ip":
            payload = request_json("GET", f"/asset/host/{value}")
        elif kind == "domain":
            body = {
                "query": f'host.services.cert.names = "{value}"',
                "page_size": 25,
                "fields": [
                    "host.ip",
                    "host.services.port",
                    "host.services.protocol",
                    "host.services.cert.names",
                ],
            }
            payload = request_json("POST", "/search/query", body)
        else:
            print(f"unsupported seed type: {kind}", file=sys.stderr)
            return 2
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        print(json.dumps({"http_status": exc.code, "error": detail}), file=sys.stderr)
        return 4
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 5
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
