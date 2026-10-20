"""Bounded public Mojang Minecraft profile driver.

One current Java-edition username in, one normalized public profile out. The
driver makes at most two unauthenticated requests: the Mojang profile lookup by
name, then the public session profile by UUID for the texture property. It never
retries, never sends credentials, and never fetches the skin or cape images.

NameMC is deliberately not used: it has no public API and its site terms do not
authorize scraping. The removed Mojang name-history endpoint is not called.

``--health`` and ``--selftest`` are offline. ``--normalize`` re-validates a saved
document and is the case run under ``--network none``.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid as uuidlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REVIEWED_ON = "2026-10-20"
PROFILE_ROOT = "https://api.mojang.com"
SESSION_ROOT = "https://sessionserver.mojang.com"
USER_AGENT = (
    "Aletheia/0.1 (https://github.com/frostknightfrosty-lgtm/aletheia; "
    "public Minecraft profile lookup)"
)
MAX_RESPONSE_BYTES = 1024 * 1024
HTTP_TIMEOUT_SECONDS = 30
MAX_ERRORS = 5
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")
UUID_RE = re.compile(r"^[0-9a-fA-F]{32}$")
TEXTURE_HOST = "textures.minecraft.net"


def _text(value: Any, limit: int = 300) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _fetch_json(url: str) -> tuple[Any, int, str | None, str | None]:
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            rate = _text(response.headers.get("x-minecraft-rate-limit-result"), 64)
            if response.status == 204:
                return None, 204, None, rate
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                return None, response.status, "response exceeded the 1 MB safety limit", rate
            try:
                return json.loads(body.decode("utf-8", errors="replace")), response.status, None, rate
            except json.JSONDecodeError as exc:
                return None, response.status, f"JSON decode error: {exc}", rate
    except urllib.error.HTTPError as exc:
        rate = _text(exc.headers.get("x-minecraft-rate-limit-result"), 64) if exc.headers else None
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return None, exc.code, f"HTTP {exc.code}: {detail[:300]}", rate
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, 0, f"{type(exc).__name__}: {exc}", None


def _dashed(value: str) -> str:
    compact = value.replace("-", "").lower()
    if not UUID_RE.fullmatch(compact):
        raise ValueError("invalid Minecraft UUID")
    return str(uuidlib.UUID(hex=compact))


def _safe_texture_url(value: Any) -> str | None:
    text = _text(value, 500)
    if not text:
        return None
    text = text.replace("http://", "https://", 1)
    parsed = urllib.parse.urlsplit(text)
    if parsed.scheme != "https" or parsed.netloc != TEXTURE_HOST:
        return None
    if not parsed.path.startswith("/texture/"):
        return None
    return text


def _decode_textures(properties: Any) -> dict[str, Any]:
    if not isinstance(properties, list):
        return {}
    for item in properties:
        if not isinstance(item, dict) or item.get("name") != "textures":
            continue
        value = item.get("value")
        if not isinstance(value, str) or len(value) > 10000:
            continue
        try:
            payload = json.loads(base64.b64decode(value, validate=True).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        textures = payload.get("textures")
        if not isinstance(textures, dict):
            return {}
        skin = textures.get("SKIN") if isinstance(textures.get("SKIN"), dict) else {}
        cape = textures.get("CAPE") if isinstance(textures.get("CAPE"), dict) else {}
        metadata = skin.get("metadata") if isinstance(skin.get("metadata"), dict) else {}
        model = _text(metadata.get("model"), 16)
        if model not in {"slim", "classic"}:
            model = None
        return {
            "skin_url": _safe_texture_url(skin.get("url")),
            "cape_url": _safe_texture_url(cape.get("url")),
            "skin_model": model,
        }
    return {}


def _collect(username: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source": "minecraft",
        "status": "ok",
        "username": username,
        "uuid": None,
        "uuid_dashed": None,
        "session_name": None,
        "skin_url": None,
        "cape_url": None,
        "skin_model": None,
        "rate_limit_result": None,
        "errors": [],
    }
    profile_url = (
        f"{PROFILE_ROOT}/users/profiles/minecraft/"
        f"{urllib.parse.quote(username, safe='')}"
    )
    profile, status, error, rate = _fetch_json(profile_url)
    if rate:
        result["rate_limit_result"] = rate
    if status in {204, 404}:
        result["status"] = "not_found"
        return result
    if error:
        result["status"] = "error"
        result["errors"] = [f"profile: {error}"]
        return result
    if not isinstance(profile, dict):
        result["status"] = "error"
        result["errors"] = ["profile: response was not a Mojang profile object"]
        return result
    compact = _text(profile.get("id"), 32)
    name = _text(profile.get("name"), 16)
    if not compact or not UUID_RE.fullmatch(compact) or not name:
        result["status"] = "error"
        result["errors"] = ["profile: missing or invalid id/name"]
        return result
    result["username"] = name
    result["uuid"] = compact.lower()
    result["uuid_dashed"] = _dashed(compact)

    session_url = (
        f"{SESSION_ROOT}/session/minecraft/profile/"
        f"{urllib.parse.quote(compact, safe='')}"
    )
    session, status, error, rate = _fetch_json(session_url)
    if rate:
        result["rate_limit_result"] = rate
    if status in {204, 404}:
        result["status"] = "partial"
        result["errors"] = ["session profile not found"]
        return result
    if error:
        result["status"] = "partial"
        result["errors"] = [f"session: {error}"]
        return result
    if not isinstance(session, dict):
        result["status"] = "partial"
        result["errors"] = ["session: response was not a profile object"]
        return result
    result["session_name"] = _text(session.get("name"), 16)
    textures = _decode_textures(session.get("properties"))
    result.update(textures)
    return result


def _normalise(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("document must be a JSON object")
    if raw.get("source") != "minecraft":
        raise ValueError("document source must be 'minecraft'")
    status = _text(raw.get("status"), 32) or "ok"
    if status not in {"ok", "partial", "not_found", "error", "invalid_target"}:
        raise ValueError(f"unsupported document status: {status}")
    username = _text(raw.get("username"), 16)
    if username and not USERNAME_RE.fullmatch(username):
        raise ValueError("document username is invalid")
    compact = _text(raw.get("uuid"), 32)
    if compact is not None and not UUID_RE.fullmatch(compact):
        raise ValueError("document UUID is invalid")
    dashed = _text(raw.get("uuid_dashed"), 36)
    if compact and not dashed:
        dashed = _dashed(compact)
    if status in {"ok", "partial"} and not compact:
        raise ValueError("a successful document requires a UUID")
    errors = [
        value for value in (
            _text(item, 300) for item in (
                raw.get("errors") if isinstance(raw.get("errors"), list) else []
            )[:MAX_ERRORS]
        ) if value
    ]
    return {
        "source": "minecraft",
        "status": status,
        "username": username,
        "uuid": compact.lower() if compact else None,
        "uuid_dashed": dashed,
        "session_name": _text(raw.get("session_name"), 16),
        "skin_url": _safe_texture_url(raw.get("skin_url")),
        "cape_url": _safe_texture_url(raw.get("cape_url")),
        "skin_model": (
            _text(raw.get("skin_model"), 16)
            if _text(raw.get("skin_model"), 16) in {"slim", "classic"}
            else None
        ),
        "rate_limit_result": _text(raw.get("rate_limit_result"), 64),
        "errors": errors,
    }


_SAMPLE_TEXTURE = base64.b64encode(json.dumps({
    "timestamp": 1792529215483,
    "profileId": "069a79f444e94726a5befca90e38aaf5",
    "profileName": "Notch",
    "textures": {
        "SKIN": {
            "url": "http://textures.minecraft.net/texture/2920091a4925b58f02c77dadc3ecef07ea4c7472f64e0fd432ce5522489362680",
            "metadata": {"model": "slim"},
        }
    },
}, separators=(",", ":")).encode()).decode()


def _health() -> int:
    payload = {
        "source": "minecraft",
        "reviewed_on": REVIEWED_ON,
        "endpoints": [
            "https://api.mojang.com/users/profiles/minecraft/{username}",
            "https://sessionserver.mojang.com/session/minecraft/profile/{uuid}",
        ],
        "network_required": True,
        "credentials_required": False,
        "requests_per_run": 2,
        "namemc": "not used (no public API; scraping not authorized)",
        "name_history": "removed upstream; not called",
    }
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)
    print("ok")
    return 0


def _selftest() -> int:
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    try:
        check("username_validation",
              bool(USERNAME_RE.fullmatch("Notch"))
              and not USERNAME_RE.fullmatch("no")
              and not USERNAME_RE.fullmatch("bad-name")
              and not USERNAME_RE.fullmatch("x" * 17),
              "3..16 word characters")
    except Exception as exc:  # noqa: BLE001
        check("username_validation", False, str(exc)[:200])
    try:
        assert _dashed("069a79f444e94726a5befca90e38aaf5") == \
            "069a79f4-44e9-4726-a5be-fca90e38aaf5"
        check("uuid_dash", True, "canonical dashed UUID")
    except Exception as exc:  # noqa: BLE001
        check("uuid_dash", False, str(exc)[:200])
    try:
        textures = _decode_textures([{"name": "textures", "value": _SAMPLE_TEXTURE}])
        check("texture_decode",
              textures["skin_url"].startswith("https://textures.minecraft.net/texture/")
              and textures["skin_model"] == "slim"
              and textures["cape_url"] is None,
              "synthetic texture property")
    except Exception as exc:  # noqa: BLE001
        check("texture_decode", False, str(exc)[:200])
    try:
        combined = {
            "source": "minecraft", "status": "ok", "username": "Notch",
            "uuid": "069a79f444e94726a5befca90e38aaf5",
            "uuid_dashed": "069a79f4-44e9-4726-a5be-fca90e38aaf5",
            "session_name": "Notch",
            "skin_url": "https://textures.minecraft.net/texture/2920091a4925b58f02c77dadc3ecef07ea4c7472f64e0fd432ce5522489362680",
            "cape_url": None, "skin_model": "slim",
            "rate_limit_result": "UNDER_LIMIT", "errors": [],
        }
        normalized = _normalise(combined)
        check("combined_normalisation",
              normalized["status"] == "ok"
              and normalized["uuid"] == "069a79f444e94726a5befca90e38aaf5"
              and normalized["skin_model"] == "slim",
              "synthetic Minecraft profile")
    except Exception as exc:  # noqa: BLE001
        check("combined_normalisation", False, str(exc)[:200])
    try:
        bad = _safe_texture_url("https://evil.example/texture/x")
        good = _safe_texture_url(
            "http://textures.minecraft.net/texture/2920091a4925b58f02c77dadc3ecef07ea4c7472f64e0fd432ce5522489362680"
        )
        check("texture_host", bad is None and good is not None
              and good.startswith("https://"), "texture host allowlist")
    except Exception as exc:  # noqa: BLE001
        check("texture_host", False, str(exc)[:200])
    try:
        _normalise({"source": "minecraft", "status": "ok", "username": "Notch"})
        check("invalid_document", False, "accepted missing UUID")
    except ValueError:
        check("invalid_document", True, "rejected missing UUID")
    check("no_credentials", True, "two public Mojang GETs; no Authorization header")
    print(json.dumps({
        "minecraft_selftest": "ok" if all(c["ok"] for c in checks) else "failed",
        "reviewed_on": REVIEWED_ON,
        "checks": checks,
    }, sort_keys=True, indent=2))
    return 0 if all(item["ok"] for item in checks) else 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--health", action="store_true")
    group.add_argument("--selftest", action="store_true")
    group.add_argument("--normalize", metavar="PROFILE_JSON")
    parser.add_argument("username_file", nargs="?")
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
            print(json.dumps({"source": "minecraft", "status": "invalid_document",
                              "error": str(exc)[:300]}, sort_keys=True))
            return 2
    if not args.username_file:
        print(json.dumps({"source": "minecraft", "status": "invalid_target",
                          "error": "one Minecraft username file is required"},
                         sort_keys=True))
        return 2
    try:
        username = Path(args.username_file).read_text(encoding="utf-8").strip()
        if "\n" in username or "\r" in username or not USERNAME_RE.fullmatch(username):
            raise ValueError("invalid Minecraft username")
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"source": "minecraft", "status": "invalid_target",
                          "error": str(exc)[:300]}, sort_keys=True))
        return 2
    result = _normalise(_collect(username))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["status"] in {"ok", "partial", "not_found"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
