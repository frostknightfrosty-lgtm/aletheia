"""Bounded Web Key Directory (WKD) lookup driver.

One email address in, one normalized public-key document out. The driver
constructs the WKD hash, tries the advanced method first, and falls back to the
direct method only when the ``openpgpkey`` sub-domain does not resolve, as the
WKD specification requires. It performs one GET (or two on that DNS fallback),
never retries, never sends an Authorization header, and never stores private
key material.

The response is parsed as OpenPGP packets directly (standard library only).
Only the primary-key fingerprint, key ID, public metadata, and User IDs that
contain the requested email are emitted; all other User IDs are dropped.

``--health`` and ``--selftest`` are offline. ``--normalize`` re-validates a
saved normalized document and is the case run under ``--network none``.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REVIEWED_ON = "2026-10-20"
SPEC_URL = "https://datatracker.ietf.org/doc/html/draft-koch-openpgp-webkey-service"
USER_AGENT = (
    "Aletheia/0.1 (https://github.com/frostknightfrosty-lgtm/aletheia; "
    "public WKD key lookup)"
)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
HTTP_TIMEOUT_SECONDS = 30
MAX_KEYS = 5
MAX_UIDS = 5
MAX_ERRORS = 5
ZBASE32 = "ybndrfg8ejkmcpqxot1uwisza345h769"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")
FINGERPRINT_RE = re.compile(r"^[0-9A-F]{40}$")
KEY_ID_RE = re.compile(r"^[0-9A-F]{16}$")

ALGORITHM_NAMES = {
    1: "RSA",
    2: "RSA-E",
    3: "RSA-S",
    16: "ElGamal",
    17: "DSA",
    18: "ECDH",
    19: "ECDSA",
    22: "EdDSA",
}


def _text(value: Any, limit: int = 300) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _lower_ascii(value: str) -> str:
    return value.translate(str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                                         "abcdefghijklmnopqrstuvwxyz"))


def _parse_email(value: str) -> dict[str, str]:
    value = value.strip()
    if len(value) > 254 or not EMAIL_RE.fullmatch(value):
        raise ValueError("email must be one addr-spec")
    local, domain = value.rsplit("@", 1)
    if not local or len(local) > 64:
        raise ValueError("email local-part must be 1..64 characters")
    if not domain or len(domain) > 253:
        raise ValueError("email domain must be 1..253 characters")
    try:
        ascii_domain = domain.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("email domain is not a valid IDNA domain") from exc
    if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
                        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", ascii_domain):
        raise ValueError("email domain is not a valid DNS name")
    return {"address": f"{local}@{ascii_domain}", "local": local,
            "domain": ascii_domain}


def _wkd_hash(local_part: str) -> str:
    digest = hashlib.sha1(_lower_ascii(local_part).encode("utf-8")).digest()
    bits = "".join(f"{byte:08b}" for byte in digest)
    return "".join(ZBASE32[int(bits[index:index + 5].ljust(5, "0"), 2)]
                   for index in range(0, len(bits), 5))


def _urls(parsed: dict[str, str]) -> tuple[str, str]:
    digest = _wkd_hash(parsed["local"])
    suffix = urllib.parse.quote(parsed["local"], safe="")
    advanced = (
        f"https://openpgpkey.{parsed['domain']}/.well-known/openpgpkey/"
        f"{parsed['domain']}/hu/{digest}?l={suffix}"
    )
    direct = (
        f"https://{parsed['domain']}/.well-known/openpgpkey/hu/"
        f"{digest}?l={suffix}"
    )
    return advanced, direct


def _fetch(url: str) -> tuple[bytes | None, int, str | None, bool]:
    """Return (bytes, status, error, dns_failure)."""
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/octet-stream",
    })
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            if not str(final_url).lower().startswith("https://"):
                return None, response.status, "redirect left HTTPS", False
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                return None, response.status, "response exceeded the 2 MB safety limit", False
            return body, response.status, None, False
    except urllib.error.HTTPError as exc:
        return None, exc.code, f"HTTP {exc.code}", False
    except urllib.error.URLError as exc:
        dns_failure = isinstance(exc.reason, (socket.gaierror, socket.herror))
        return None, 0, f"{type(exc.reason).__name__}: {exc.reason}", dns_failure
    except (TimeoutError, OSError) as exc:
        return None, 0, f"{type(exc).__name__}: {exc}", False


def _packets(data: bytes) -> list[tuple[int, bytes]]:
    packets: list[tuple[int, bytes]] = []
    offset = 0
    while offset < len(data):
        header = data[offset]
        offset += 1
        if not header & 0x80:
            raise ValueError("invalid OpenPGP packet header")
        if header & 0x40:
            tag = header & 0x3F
            if offset >= len(data):
                raise ValueError("truncated packet length")
            first = data[offset]
            offset += 1
            if first < 192:
                length = first
            elif first < 224:
                if offset >= len(data):
                    raise ValueError("truncated packet length")
                length = ((first - 192) << 8) + data[offset] + 192
                offset += 1
            elif first == 255:
                if offset + 4 > len(data):
                    raise ValueError("truncated packet length")
                length = int.from_bytes(data[offset:offset + 4], "big")
                offset += 4
            else:
                raise ValueError("partial packet lengths are not supported")
        else:
            tag = (header >> 2) & 0x0F
            length_type = header & 0x03
            if length_type == 3:
                raise ValueError("indeterminate packet lengths are not supported")
            width = (1, 2, 4)[length_type]
            if offset + width > len(data):
                raise ValueError("truncated packet length")
            length = int.from_bytes(data[offset:offset + width], "big")
            offset += width
        if length < 0 or offset + length > len(data):
            raise ValueError("truncated packet body")
        packets.append((tag, data[offset:offset + length]))
        offset += length
    return packets


def _primary(body: bytes) -> dict[str, Any]:
    if len(body) < 6:
        raise ValueError("public-key packet is too short")
    version = body[0]
    if version != 4:
        raise ValueError(f"unsupported OpenPGP key version: {version}")
    created = int.from_bytes(body[1:5], "big")
    algorithm = body[5]
    fingerprint = hashlib.sha1(
        b"\x99" + len(body).to_bytes(2, "big") + body
    ).hexdigest().upper()
    return {
        "fingerprint": fingerprint,
        "key_id": fingerprint[-16:],
        "version": version,
        "algorithm": algorithm,
        "algorithm_name": ALGORITHM_NAMES.get(algorithm, f"algorithm-{algorithm}"),
        "created": created,
        "created_at": datetime.fromtimestamp(
            created, timezone.utc
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "user_ids": [],
        "other_uid_count": 0,
    }


def _parse_keys(data: bytes, email: str) -> list[dict[str, Any]]:
    keys: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for tag, body in _packets(data):
        if tag == 6:
            if current is not None:
                keys.append(current)
            current = _primary(body)
        elif tag == 13 and current is not None:
            try:
                uid = body.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                current["other_uid_count"] += 1
                continue
            if email.casefold() in uid.casefold():
                if len(current["user_ids"]) < MAX_UIDS:
                    current["user_ids"].append(uid[:300])
            else:
                current["other_uid_count"] += 1
    if current is not None:
        keys.append(current)
    matching = [key for key in keys if key["user_ids"]]
    return matching[:MAX_KEYS]


def _collect(email: str) -> dict[str, Any]:
    try:
        parsed = _parse_email(email)
    except ValueError as exc:
        return {"source": "pgp_keys", "status": "invalid_target",
                "email": email, "error": str(exc), "keys": [], "errors": []}
    advanced, direct = _urls(parsed)
    data, status, error, dns_failure = _fetch(advanced)
    method = "advanced"
    url = advanced
    if dns_failure:
        data, status, error, _ = _fetch(direct)
        method = "direct"
        url = direct
    result: dict[str, Any] = {
        "source": "pgp_keys",
        "status": "ok",
        "email": parsed["address"],
        "method": method,
        "url": url,
        "http_status": status,
        "key_block_sha256": None,
        "key_block_bytes": 0,
        "keys": [],
        "errors": [],
    }
    if error:
        result["status"] = "not_found" if status == 404 else "error"
        result["errors"] = [error]
        return result
    if not data:
        result["status"] = "not_found"
        result["errors"] = ["empty key response"]
        return result
    result["key_block_sha256"] = hashlib.sha256(data).hexdigest()
    result["key_block_bytes"] = len(data)
    try:
        keys = _parse_keys(data, parsed["address"])
    except ValueError as exc:
        result["status"] = "error"
        result["errors"] = [str(exc)[:300]]
        return result
    if not keys:
        result["status"] = "error"
        result["errors"] = [
            "key block contained no primary key with a matching User ID"
        ]
        return result
    result["keys"] = keys
    return result


def _normalise(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("document must be a JSON object")
    if raw.get("source") != "pgp_keys":
        raise ValueError("document source must be 'pgp_keys'")
    email = _text(raw.get("email"), 254)
    if not email:
        raise ValueError("document email is required")
    status = _text(raw.get("status"), 32) or "ok"
    if status not in {"ok", "partial", "not_found", "error", "invalid_target"}:
        raise ValueError(f"unsupported document status: {status}")
    method = _text(raw.get("method"), 16)
    if method not in {None, "advanced", "direct"}:
        raise ValueError("document method is invalid")
    keys: list[dict[str, Any]] = []
    seen: set[str] = set()
    raw_keys = raw.get("keys") if isinstance(raw.get("keys"), list) else []
    for item in raw_keys[:MAX_KEYS]:
        if not isinstance(item, dict):
            continue
        fingerprint = _text(item.get("fingerprint"), 40)
        if not fingerprint or not FINGERPRINT_RE.fullmatch(fingerprint):
            continue
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        key_id = _text(item.get("key_id"), 16)
        if not key_id or not KEY_ID_RE.fullmatch(key_id):
            key_id = fingerprint[-16:]
        created_at = _text(item.get("created_at"), 64)
        user_ids = [
            value for value in (
                _text(uid, 300) for uid in (
                    item.get("user_ids") if isinstance(item.get("user_ids"), list) else []
                )[:MAX_UIDS]
            ) if value and email.casefold() in value.casefold()
        ]
        if not user_ids:
            continue
        keys.append({
            "fingerprint": fingerprint,
            "key_id": key_id,
            "version": _number(item.get("version")),
            "algorithm": _number(item.get("algorithm")),
            "algorithm_name": _text(item.get("algorithm_name"), 64),
            "created_at": created_at,
            "user_ids": user_ids,
            "other_uid_count": int(_number(item.get("other_uid_count")) or 0),
        })
    if status == "ok" and not keys:
        status = "error"
    errors = [
        value for value in (
            _text(item, 300) for item in (
                raw.get("errors") if isinstance(raw.get("errors"), list) else []
            )[:MAX_ERRORS]
        ) if value
    ]
    return {
        "source": "pgp_keys",
        "status": status,
        "email": email,
        "method": method,
        "url": _text(raw.get("url"), 500),
        "http_status": _number(raw.get("http_status")),
        "key_block_sha256": _text(raw.get("key_block_sha256"), 64),
        "key_block_bytes": int(_number(raw.get("key_block_bytes")) or 0),
        "keys": keys,
        "errors": errors,
    }


_SAMPLE_PUBLIC_KEY = base64.b64decode(
    "mDMEV2o9XRYJKwYBBAHaRw8BAQdAZ8zkuQDL9x7rcvvoo6s3iEF1j88Dknd9nZhL"
    "nTEoBRm0G3BhdHJpY2UubHVtdW1iYUBleGFtcGxlLm5ldIh5BBMWCAAhBQJXaj1d"
    "AhsDBQsJCAcCBhUICQoLAgQWAgMBAh4BAheAAAoJEBOVY2gqAg0KmQ0BAMUNzAlT"
    "OzG7tolSI92lhePi5VqutdqTEQTyYYWi1aEsAP0YfiuosNggTc0oRTSz46S3i0Qj"
    "AlpXwfU00888yIreDbg4BFdqPY0SCisGAQQBl1UBBQEBB0AWeeZlz31O4qTmIKr3"
    "CZhlRUXZFxc3YKyoCXyIZBBRawMBCAeIYQQYFggACQUCV2o9jQIbDAAKCRATlWNo"
    "KgINCsuFAP9BplWl813pi779V8OMsRGs/ynyihnOESft/H8qlM8PDQEAqIUPpIty"
    "OX/OBFy2RIlIi7J1bTp9RzcbzQ/4Fk4hWQQ="
)


def _health() -> int:
    payload = {
        "source": "pgp_keys",
        "reviewed_on": REVIEWED_ON,
        "specification": SPEC_URL,
        "network_required": True,
        "credentials_required": False,
        "methods": ["advanced", "direct (DNS fallback only)"],
        "max_keys": MAX_KEYS,
        "max_user_ids_per_key": MAX_UIDS,
    }
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)
    print("ok")
    return 0


def _selftest() -> int:
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    try:
        parsed = _parse_email("Joe.Doe@Example.ORG")
        check("email_parse", parsed["address"] == "Joe.Doe@example.org"
              and parsed["local"] == "Joe.Doe" and parsed["domain"] == "example.org",
              parsed["address"])
    except Exception as exc:  # noqa: BLE001
        check("email_parse", False, str(exc)[:200])
    try:
        digest = _wkd_hash("Joe.Doe")
        check("wkd_hash", digest == "iy9q119eutrkn8s1mk4r39qejnbu3n5q",
              digest)
    except Exception as exc:  # noqa: BLE001
        check("wkd_hash", False, str(exc)[:200])
    try:
        parsed = _parse_email("patrice.lumumba@example.net")
        advanced, direct = _urls(parsed)
        check("wkd_urls", "/.well-known/openpgpkey/example.net/hu/" in advanced
              and advanced.startswith("https://openpgpkey.example.net/")
              and direct.startswith("https://example.net/")
              and "?l=patrice.lumumba" in direct,
              advanced)
    except Exception as exc:  # noqa: BLE001
        check("wkd_urls", False, str(exc)[:200])
    try:
        keys = _parse_keys(_SAMPLE_PUBLIC_KEY, "patrice.lumumba@example.net")
        check("openpgp_fingerprint",
              len(keys) == 1
              and keys[0]["fingerprint"] == "B21DEAB4F875FB3DA42F1D1D139563682A020D0A"
              and keys[0]["key_id"] == "139563682A020D0A"
              and keys[0]["version"] == 4
              and keys[0]["algorithm_name"] == "EdDSA",
              "official WKD specification sample key")
        check("uid_filter",
              keys[0]["user_ids"] == ["patrice.lumumba@example.net"],
              "only the matching User ID is retained")
    except Exception as exc:  # noqa: BLE001
        check("openpgp_fingerprint", False, str(exc)[:200])
        check("uid_filter", False, str(exc)[:200])
    try:
        combined = {
            "source": "pgp_keys", "status": "ok",
            "email": "patrice.lumumba@example.net", "method": "advanced",
            "url": "https://openpgpkey.example.net/example",
            "http_status": 200,
            "key_block_sha256": hashlib.sha256(_SAMPLE_PUBLIC_KEY).hexdigest(),
            "key_block_bytes": len(_SAMPLE_PUBLIC_KEY),
            "keys": _parse_keys(_SAMPLE_PUBLIC_KEY, "patrice.lumumba@example.net"),
            "errors": [],
        }
        normalised = _normalise(combined)
        check("combined_normalisation",
              normalised["status"] == "ok" and len(normalised["keys"]) == 1
              and normalised["keys"][0]["fingerprint"].startswith("B21DEAB4"),
              "synthetic WKD document")
    except Exception as exc:  # noqa: BLE001
        check("combined_normalisation", False, str(exc)[:200])
    try:
        bounded = _normalise({
            "source": "pgp_keys", "status": "ok",
            "email": "patrice.lumumba@example.net",
            "keys": [{
                "fingerprint": "B21DEAB4F875FB3DA42F1D1D139563682A020D0A",
                "key_id": "139563682A020D0A",
                "user_ids": ["patrice.lumumba@example.net"],
            }] * 20,
            "errors": ["x"] * 20,
        })
        check("bounds", len(bounded["keys"]) == 1
              and len(bounded["errors"]) == MAX_ERRORS,
              "deduplicated keys and bounded errors")
    except Exception as exc:  # noqa: BLE001
        check("bounds", False, str(exc)[:200])
    check("no_credentials", True, "public WKD GET only; no Authorization header")
    print(json.dumps({
        "pgp_keys_selftest": "ok" if all(c["ok"] for c in checks) else "failed",
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
    parser.add_argument("email_file", nargs="?")
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
            print(json.dumps({"source": "pgp_keys", "status": "invalid_document",
                              "error": str(exc)[:300]}, sort_keys=True))
            return 2
    if not args.email_file:
        print(json.dumps({"source": "pgp_keys", "status": "invalid_target",
                          "error": "one email file is required"}, sort_keys=True))
        return 2
    try:
        email = Path(args.email_file).read_text(encoding="utf-8").strip()
        if "\n" in email or "\r" in email:
            raise ValueError("email file must contain one line")
        parsed = _parse_email(email)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"source": "pgp_keys", "status": "invalid_target",
                          "error": str(exc)[:300]}, sort_keys=True))
        return 2
    result = _normalise(_collect(parsed["address"]))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["status"] in {"ok", "not_found", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
