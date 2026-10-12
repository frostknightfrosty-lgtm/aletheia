from __future__ import annotations

import ipaddress
import json
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import quote, urljoin, urlsplit


BOOTSTRAP_URLS = {
    "domain": "https://data.iana.org/rdap/dns.json",
    "ipv4": "https://data.iana.org/rdap/ipv4.json",
    "ipv6": "https://data.iana.org/rdap/ipv6.json",
}
MAX_RESPONSE_BYTES = 1_000_000
USER_AGENT = "Aletheia/0.7.0 (RDAP; RFC 9082)"


class _HTTPSOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme.lower() != "https":
            raise urllib.error.URLError("RDAP redirects must remain HTTPS")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def normalize_domain(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    candidate = value if "://" in value else f"//{value}"
    try:
        parts = urlsplit(candidate)
        if parts.scheme and parts.scheme.lower() not in {"http", "https"}:
            return None
        if parts.username is not None or parts.password is not None:
            return None
        hostname = parts.hostname
    except ValueError:
        return None
    if not hostname:
        return None
    try:
        domain = hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None
    labels = domain.split(".")
    if len(domain) > 253 or len(labels) < 2:
        return None
    if any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or not all(char.isascii() and (char.isalnum() or char == "-") for char in label)
        for label in labels
    ):
        return None
    return domain


def _valid_https_base(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if (parts.scheme.lower() != "https" or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment):
        return None
    return value.rstrip("/") + "/"


def _fetch_json(url: str) -> object:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/rdap+json, application/json", "User-Agent": USER_AGENT},
    )
    opener = urllib.request.build_opener(_HTTPSOnlyRedirectHandler())
    with opener.open(request, timeout=30) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("RDAP response exceeded the 1 MB safety limit")
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("RDAP response was not valid JSON") from exc


def _domain_base(bootstrap: object, domain: str) -> str | None:
    if not isinstance(bootstrap, dict) or not isinstance(bootstrap.get("services"), list):
        return None
    matches: list[tuple[int, str]] = []
    for service in bootstrap["services"]:
        if not isinstance(service, list) or len(service) != 2:
            continue
        suffixes, urls = service
        if not isinstance(suffixes, list) or not isinstance(urls, list):
            continue
        for suffix in suffixes:
            if not isinstance(suffix, str):
                continue
            try:
                normalized_suffix = suffix.rstrip(".").encode("idna").decode("ascii").lower()
            except UnicodeError:
                continue
            if domain == normalized_suffix or domain.endswith("." + normalized_suffix):
                for candidate in urls:
                    base = _valid_https_base(candidate)
                    if base:
                        matches.append((len(normalized_suffix), base))
    return max(matches, key=lambda item: item[0])[1] if matches else None


def _ip_base(bootstrap: object, address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    if not isinstance(bootstrap, dict) or not isinstance(bootstrap.get("services"), list):
        return None
    matches: list[tuple[int, str]] = []
    for service in bootstrap["services"]:
        if not isinstance(service, list) or len(service) != 2:
            continue
        prefixes, urls = service
        if not isinstance(prefixes, list) or not isinstance(urls, list):
            continue
        for prefix in prefixes:
            if not isinstance(prefix, str):
                continue
            try:
                network = ipaddress.ip_network(prefix, strict=False)
            except ValueError:
                continue
            if network.version == address.version and address in network:
                for candidate in urls:
                    base = _valid_https_base(candidate)
                    if base:
                        matches.append((network.prefixlen, base))
    return max(matches, key=lambda item: item[0])[1] if matches else None


def _domain_matches(record: dict, domain: str) -> bool:
    names = [record[field] for field in ("ldhName", "unicodeName") if isinstance(record.get(field), str)]
    normalized_names = [normalize_domain(value) for value in names]
    return bool(normalized_names) and all(value == domain for value in normalized_names)


def _ip_matches(record: dict, address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    try:
        start = ipaddress.ip_address(record.get("startAddress", ""))
        end = ipaddress.ip_address(record.get("endAddress", ""))
    except (ValueError, TypeError):
        return False
    return start.version == address.version == end.version and int(start) <= int(address) <= int(end)


def curate_domain(record: object, domain: str) -> dict | None:
    if not isinstance(record, dict) or not _domain_matches(record, domain):
        return None
    curated: dict[str, object] = {}
    for field in ("handle", "ldhName", "unicodeName"):
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            curated[field] = value
    statuses = record.get("status")
    if isinstance(statuses, list):
        curated["status"] = [value for value in statuses if isinstance(value, str)]
    events = record.get("events")
    if isinstance(events, list):
        curated["events"] = [
            {key: event[key] for key in ("eventAction", "eventDate") if isinstance(event.get(key), str)}
            for event in events if isinstance(event, dict)
        ]
    nameservers = record.get("nameservers")
    if isinstance(nameservers, list):
        curated["nameservers"] = [
            item["ldhName"] for item in nameservers
            if isinstance(item, dict) and isinstance(item.get("ldhName"), str)
        ]
    secure_dns = record.get("secureDNS")
    if isinstance(secure_dns, dict) and isinstance(secure_dns.get("delegationSigned"), bool):
        curated["secureDNS"] = {"delegationSigned": secure_dns["delegationSigned"]}
    return curated


def curate_ip(record: object, address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> dict | None:
    if not isinstance(record, dict) or not _ip_matches(record, address):
        return None
    curated: dict[str, object] = {}
    for field in ("handle", "type", "startAddress", "endAddress", "ipVersion", "country", "parentHandle"):
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            curated[field] = value
    network_name = record.get("name")
    if isinstance(network_name, str) and network_name.strip():
        curated["network_name"] = network_name
    statuses = record.get("status")
    if isinstance(statuses, list):
        curated["status"] = [value for value in statuses if isinstance(value, str)]
    return curated


def lookup(kind: str, value: str) -> tuple[dict | None, str | None, int]:
    """Perform one IANA bootstrap fetch and at most one exact HTTPS RDAP lookup."""
    if kind == "domain":
        seed = normalize_domain(value)
        if seed is None:
            return None, "invalid_domain_seed", 0
        bootstrap_url = BOOTSTRAP_URLS["domain"]
    elif kind == "ip":
        try:
            address = ipaddress.ip_address(value.strip())
        except (ValueError, TypeError):
            return None, "invalid_ip_seed", 0
        seed = str(address)
        bootstrap_url = BOOTSTRAP_URLS["ipv4" if address.version == 4 else "ipv6"]
    else:
        return None, "unsupported_seed_type", 2

    try:
        bootstrap = _fetch_json(bootstrap_url)
        base = _domain_base(bootstrap, seed) if kind == "domain" else _ip_base(bootstrap, address)
        if not base:
            return None, "no_https_rdap_service_in_iana_bootstrap", 0
        path = f"{kind}/{quote(seed, safe=':')}"
        query_url = urljoin(base, path)
        response = _fetch_json(query_url)
        record = curate_domain(response, seed) if kind == "domain" else curate_ip(response, address)
        if record is None:
            return None, "rdap_record_did_not_match_exact_seed", 0
        return {"query_url": query_url, "record": record}, None, 0
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None, "rdap_record_not_found", 0
        return None, f"rdap_http_error_{exc.code}", 4
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, f"rdap_network_error_{type(exc).__name__}", 5
    except ValueError as exc:
        return None, f"rdap_response_error: {exc}", 4


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["--health"]:
        print("ok")
        return 0
    if len(args) != 2 or args[0] not in {"domain", "ip"}:
        print("usage: runner.py <domain|ip> <seed>", file=sys.stderr)
        return 2

    result, reason, exit_code = lookup(args[0], args[1])
    if result is not None:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps({"status": "empty", "reason": reason}, sort_keys=True))
        print(f"RDAP produced no finding: {reason}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
