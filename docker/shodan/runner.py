import json
import os
import sys

from shodan import Shodan


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--health":
        print("ok")
        return 0
    if len(sys.argv) != 3:
        print("usage: runner.py <domain|ip> <value>", file=sys.stderr)
        return 2
    key = os.getenv("SHODAN_API_KEY")
    if not key:
        print("SHODAN_API_KEY is required", file=sys.stderr)
        return 3
    kind, value = sys.argv[1], sys.argv[2]
    api = Shodan(key)
    if kind == "domain":
        payload = api.dns.domain(value, page=1)
    elif kind == "ip":
        payload = api.host(value, minify=True)
    else:
        print(f"unsupported seed type: {kind}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
