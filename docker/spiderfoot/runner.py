"""Bounded SpiderFoot 4.0 batch runner for the Aletheia meta-adapter.

The image is intentionally opinionated: it runs a curated set of 14 modules
instead of SpiderFoot's full 200+ module catalogue, passes every seed through
``sf.py -s <value> -t <event-type> -o json -q -m <modules>``, and emits a small
JSON envelope around SpiderFoot's JSON event array. The envelope records which
keyed modules were skipped and why, so the adapter can preserve an explicit
evidence trail instead of silently losing a source.

API keys are read from the process environment and written to SpiderFoot's
private SQLite ``tbl_config`` table in the container's writable ``/tmp`` data
directory. They are never placed in argv or in the emitted envelope.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

# SpiderFoot v4.0.0 tag. Pinning the commit (rather than the mutable tag) makes
# the image reproducible even if the upstream tag is moved.
SPIDERFOOT_COMMIT = "b9c345de5b085debc7444fc10e0e26e7745df5f2"
SPIDERFOOT_VERSION = "4.0.0"

# Curated gap-filling catalogue. Native Aletheia adapters overlap some
# SpiderFoot modules heavily (for example sfp_shodan, sfp_github and
# sfp_leakix), so those are deliberately excluded. legal_tier is descriptive
# metadata for the operator log only; it does not gate execution.
MODULES: tuple[dict[str, Any], ...] = (
    {
        "name": "sfp_threatcrowd",
        "source": "ThreatCrowd",
        "website": "https://www.threatcrowd.org/",
        "legal_tier": 1,
        "legal_label": "public no-auth passive",
        "requires_key": False,
        "env": None,
    },
    {
        "name": "sfp_threatminer",
        "source": "ThreatMiner",
        "website": "https://www.threatminer.org/",
        "legal_tier": 1,
        "legal_label": "public no-auth passive",
        "requires_key": False,
        "env": None,
    },
    {
        "name": "sfp_robtex",
        "source": "Robtex",
        "website": "https://www.robtex.com/",
        "legal_tier": 1,
        "legal_label": "public no-auth passive",
        "requires_key": False,
        "env": None,
    },
    {
        "name": "sfp_keybase",
        "source": "Keybase",
        "website": "https://keybase.io/",
        "legal_tier": 1,
        "legal_label": "public no-auth passive",
        "requires_key": False,
        "env": None,
    },
    {
        "name": "sfp_openphish",
        "source": "OpenPhish",
        "website": "https://openphish.com/",
        "legal_tier": 1,
        "legal_label": "public no-auth passive",
        "requires_key": False,
        "env": None,
    },
    {
        "name": "sfp_phishtank",
        "source": "PhishTank",
        "website": "https://phishtank.com/",
        "legal_tier": 1,
        "legal_label": "public no-auth passive",
        "requires_key": False,
        "env": None,
    },
    {
        "name": "sfp_threatfox",
        "source": "ThreatFox (abuse.ch)",
        "website": "https://threatfox.abuse.ch/",
        "legal_tier": 2,
        "legal_label": "public abuse feed, no auth",
        "requires_key": False,
        "env": None,
    },
    {
        "name": "sfp_abusech",
        "source": "abuse.ch",
        "website": "https://abuse.ch/",
        "legal_tier": 2,
        "legal_label": "public abuse feed, no auth",
        "requires_key": False,
        "env": None,
    },
    {
        "name": "sfp_emailrep",
        "source": "EmailRep",
        "website": "https://emailrep.io/",
        "legal_tier": 3,
        "legal_label": "free authenticated, rate limited",
        "requires_key": True,
        "env": "EMAILREP_API_KEY",
    },
    {
        "name": "sfp_hunter",
        "source": "Hunter",
        "website": "https://hunter.io/",
        "legal_tier": 3,
        "legal_label": "free authenticated, rate limited",
        "requires_key": True,
        "env": "HUNTER_API_KEY",
    },
    {
        "name": "sfp_pulsedive",
        "source": "Pulsedive",
        "website": "https://pulsedive.com/",
        "legal_tier": 3,
        "legal_label": "free authenticated, rate limited",
        "requires_key": True,
        "env": "PULSEDIVE_API_KEY",
    },
    {
        "name": "sfp_intelx",
        "source": "Intelligence X",
        "website": "https://intelx.io/",
        "legal_tier": 4,
        "legal_label": "commercial or leak-index source",
        "requires_key": True,
        "env": "INTELX_API_KEY",
    },
    {
        "name": "sfp_c99",
        "source": "C99",
        "website": "https://c99.nl/",
        "legal_tier": 4,
        "legal_label": "commercial or leak-index source",
        "requires_key": True,
        "env": "C99_API_KEY",
    },
    {
        "name": "sfp_haveibeenpwned",
        "source": "Have I Been Pwned",
        "website": "https://haveibeenpwned.com/",
        "legal_tier": 4,
        "legal_label": "commercial or leak-index source",
        "requires_key": True,
        "env": "HIBP_API_KEY",
    },
)

MODULE_BY_NAME: dict[str, dict[str, Any]] = {spec["name"]: spec for spec in MODULES}

# SpiderFoot's ``-t`` accepts event types; target detection itself is performed
# from ``-s``. A bare domain is detected as INTERNET_NAME, not DOMAIN_NAME.
SEED_EVENT_TYPES: dict[str, str] = {
    "domain": "INTERNET_NAME",
    "ip": "IP_ADDRESS",
    "email": "EMAILADDR",
    "username": "USERNAME",
    "phone": "PHONE_NUMBER",
}

_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_USERNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class SeedError(ValueError):
    """Raised when a CLI seed cannot be safely handed to SpiderFoot."""


def _normalize_domain(value: str) -> str:
    value = value.strip().lower().rstrip(".")
    if not value or "://" in value or "/" in value or "@" in value:
        raise SeedError("domain must be a bare hostname such as example.com")
    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise SeedError("domain is not valid IDNA") from exc
    if len(value) > 253:
        raise SeedError("domain is too long")
    labels = value.split(".")
    if len(labels) < 2 or any(not _DOMAIN_LABEL.match(label) for label in labels):
        raise SeedError("domain must be a valid fully qualified hostname")
    return value


def _normalize_email(value: str) -> str:
    value = value.strip()
    if value.count("@") != 1:
        raise SeedError("email must contain exactly one @")
    local, _, domain = value.partition("@")
    if not local or len(local) > 64 or any(ch.isspace() for ch in local):
        raise SeedError("email local part is invalid")
    return f"{local}@{_normalize_domain(domain)}"


def _normalize_username(value: str) -> str:
    value = value.strip()
    if value.startswith("@"):
        value = value[1:]
    if not _USERNAME.match(value):
        raise SeedError("username must be 1-64 letters, digits, dots, underscores or hyphens")
    return value


def _normalize_phone(value: str) -> str:
    value = value.strip()
    cleaned = re.sub(r"[\s().-]", "", value)
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not re.fullmatch(r"\+?[0-9]{7,15}", cleaned):
        raise SeedError("phone must contain 7-15 digits and an optional leading +")
    return cleaned


def parse_seed(raw: str) -> dict[str, str]:
    """Parse ``domain:example.com`` into a validated seed description."""
    if not isinstance(raw, str) or ":" not in raw:
        raise SeedError("seed must use type:value, for example domain:example.com")
    seed_type, value = raw.split(":", 1)
    seed_type = seed_type.strip().lower()
    value = value.strip()
    if not value:
        raise SeedError("seed value is empty")
    if seed_type == "domain":
        normalized = _normalize_domain(value)
    elif seed_type == "ip":
        try:
            normalized = str(ipaddress.ip_address(value))
        except ValueError as exc:
            raise SeedError("ip must be a valid IPv4 or IPv6 address") from exc
    elif seed_type == "email":
        normalized = _normalize_email(value)
    elif seed_type == "username":
        normalized = _normalize_username(value)
    elif seed_type == "phone":
        normalized = _normalize_phone(value)
    else:
        supported = ", ".join(sorted(SEED_EVENT_TYPES))
        raise SeedError(f"unsupported seed type {seed_type!r}; expected one of: {supported}")
    return {
        "type": seed_type,
        "value": normalized,
        "spiderfoot_type": SEED_EVENT_TYPES[seed_type],
    }


def select_modules(environ: Mapping[str, str] | None = None) -> tuple[list[str], list[dict[str, Any]]]:
    """Return runnable modules and explicit skip records for missing API keys."""
    env = os.environ if environ is None else environ
    runnable: list[str] = []
    skipped: list[dict[str, Any]] = []
    for spec in MODULES:
        env_name = spec["env"]
        if env_name and not env.get(env_name):
            skipped.append(
                {
                    "module": spec["name"],
                    "source": spec["source"],
                    "requires_key": True,
                    "env": env_name,
                    "legal_tier": spec["legal_tier"],
                    "reason": f"{env_name} is not set",
                }
            )
            continue
        runnable.append(spec["name"])
    return runnable, skipped


def _spiderfoot_target(seed: Mapping[str, str]) -> str:
    """Quote username seeds so SpiderFoot's target detector sees USERNAME.

    SpiderFoot wraps bare values without a dot in quotes, but a username such as
    ``john.doe`` would otherwise be classified as a domain. Quoting is the
    documented CLI convention for usernames and human names.
    """
    if seed["type"] == "username":
        return f'"{seed["value"]}"'
    return seed["value"]


def build_scan_command(seed: Mapping[str, str], modules: list[str]) -> list[str]:
    """Build the pinned SpiderFoot CLI invocation."""
    if not modules:
        raise SeedError("no SpiderFoot modules are runnable for this seed")
    return [
        "python3",
        "sf.py",
        "-s",
        _spiderfoot_target(seed),
        "-t",
        seed["spiderfoot_type"],
        "-o",
        "json",
        "-q",
        "-m",
        ",".join(modules),
    ]


def health_command() -> list[str]:
    """The offline smoke command used by the Docker capture test."""
    return ["python3", "sf.py", "-h"]


def _data_dir(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    return Path(env.get("SPIDERFOOT_DATA", "/tmp/spiderfoot"))


def _prepare_data_dir(environ: Mapping[str, str] | None = None) -> Path:
    data_dir = _data_dir(environ)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return data_dir


def _inject_api_keys(
    data_dir: Path,
    modules: list[str],
    environ: Mapping[str, str] | None = None,
) -> tuple[Path, int]:
    """Write configured API keys into SpiderFoot's private config database.

    SpiderFoot reads module options from ``tbl_config`` using
    ``scope=module name`` and ``opt=api_key``. Writing the table directly avoids
    importing SpiderFoot and avoids putting a key in a command line. The data
    directory lives under the container's writable tmpfs.
    """
    env = os.environ if environ is None else environ
    db_path = data_dir / "spiderfoot.db"
    injected = 0
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS tbl_config ("
            "scope VARCHAR NOT NULL, "
            "opt VARCHAR NOT NULL, "
            "val VARCHAR NOT NULL, "
            "PRIMARY KEY (scope, opt))"
        )
        for module in modules:
            spec = MODULE_BY_NAME.get(module)
            env_name = spec.get("env") if spec else None
            value = env.get(env_name, "") if env_name else ""
            if not value:
                continue
            connection.execute(
                "INSERT OR REPLACE INTO tbl_config (scope, opt, val) VALUES (?, ?, ?)",
                (module, "api_key", value),
            )
            injected += 1
        connection.commit()
    finally:
        connection.close()
    return db_path, injected


def _has_spiderfoot_schema(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    try:
        connection = sqlite3.connect(db_path)
        try:
            connection.execute("SELECT COUNT(*) FROM tbl_scan_config")
        finally:
            connection.close()
        return True
    except sqlite3.Error:
        return False


def _bootstrap_schema(db_path: Path, home: Path) -> None:
    """Create SpiderFoot's full schema before injecting module options.

    ``SpiderFootDb.create()`` issues plain ``CREATE TABLE`` statements, so a
    pre-created partial database containing only ``tbl_config`` would make the
    scan abort with "table already exists". Let SpiderFoot create the schema
    first, then replace the config rows.
    """
    if _has_spiderfoot_schema(db_path):
        return
    for suffix in ("", "-wal", "-shm", "-journal"):
        candidate = Path(str(db_path) + suffix)
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
    command = [
        "python3",
        "-c",
        "import sys; from spiderfoot import SpiderFootDb; "
        "SpiderFootDb({'__database': sys.argv[1]}, init=True)",
        str(db_path),
    ]
    completed = subprocess.run(
        command,
        cwd=str(home),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[-1000:]
        raise RuntimeError(f"could not initialize SpiderFoot schema: {detail}")



def _scrub_api_keys(db_path: Path) -> None:
    """Remove injected keys after the child process exits."""
    if not db_path.exists():
        return
    try:
        connection = sqlite3.connect(db_path)
        try:
            connection.execute("DELETE FROM tbl_config WHERE opt = 'api_key'")
            connection.commit()
        finally:
            connection.close()
    except sqlite3.Error:
        # The scan has already finished; a scrub failure must not hide results.
        pass


def _search_path(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    return Path(env.get("SPIDERFOOT_HOME", "/opt/spiderfoot"))


def _parse_events(stdout: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse SpiderFoot's JSON array, tolerating surrounding scaffold noise."""
    text = stdout.strip()
    if not text:
        return [], ["SpiderFoot produced no stdout"]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start < 0 or end <= start:
            return [], ["SpiderFoot stdout was not valid JSON"]
        try:
            payload = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return [], ["SpiderFoot stdout was not valid JSON"]
    if not isinstance(payload, list):
        return [], ["SpiderFoot JSON output was not an event array"]
    events = [item for item in payload if isinstance(item, dict)]
    return events, []


def _write_envelope(payload: Mapping[str, Any]) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def _run_health() -> int:
    home = _search_path()
    try:
        completed = subprocess.run(
            health_command(),
            cwd=str(home),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _write_envelope({"status": "failed", "error": str(exc), "events": []})
        return 2
    if completed.stdout:
        sys.stdout.write(completed.stdout)
    if completed.stderr:
        sys.stderr.write(completed.stderr)
    return completed.returncode


def run_scan(seed: Mapping[str, str]) -> int:
    environ = os.environ
    runnable, skipped = select_modules(environ)
    if not runnable:
        _write_envelope(
            {
                "source": "spiderfoot",
                "version": SPIDERFOOT_VERSION,
                "status": "failed",
                "seed": dict(seed),
                "modules_requested": [spec["name"] for spec in MODULES],
                "modules_run": [],
                "skipped": skipped,
                "events": [],
                "errors": ["no SpiderFoot modules are runnable"],
            }
        )
        return 2

    data_dir = _prepare_data_dir(environ)
    db_path: Path | None = None
    injected = 0
    keyed_modules = [
        module
        for module in runnable
        if (spec := MODULE_BY_NAME.get(module)) and spec.get("env") and environ.get(spec["env"])
    ]
    if keyed_modules:
        try:
            db_path = data_dir / "spiderfoot.db"
            _bootstrap_schema(db_path, _search_path(environ))
            db_path, injected = _inject_api_keys(data_dir, keyed_modules, environ)
        except (OSError, sqlite3.Error, RuntimeError, subprocess.SubprocessError) as exc:
            _write_envelope(
                {
                    "source": "spiderfoot",
                    "version": SPIDERFOOT_VERSION,
                    "status": "failed",
                    "seed": dict(seed),
                    "modules_requested": [spec["name"] for spec in MODULES],
                    "modules_run": runnable,
                    "skipped": skipped,
                    "events": [],
                    "errors": [f"could not prepare SpiderFoot config: {exc}"],
                }
            )
            return 2
    command = build_scan_command(seed, runnable)
    timeout = float(environ.get("SPIDERFOOT_TIMEOUT_SECONDS", "600"))
    errors: list[str] = []
    try:
        completed = subprocess.run(
            command,
            cwd=str(_search_path(environ)),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        exit_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        exit_code = 124
        errors.append(f"SpiderFoot scan timed out after {timeout:g}s")
    except OSError as exc:
        stdout = ""
        stderr = ""
        exit_code = 127
        errors.append(f"could not start SpiderFoot: {exc}")
    finally:
        if db_path is not None:
            _scrub_api_keys(db_path)

    events, parse_errors = _parse_events(stdout)
    errors.extend(parse_errors)
    if exit_code != 0:
        errors.append(f"SpiderFoot exited with code {exit_code}")
    status = "ok" if exit_code == 0 and not errors else "partial"
    if not events and exit_code != 0:
        status = "failed"

    _write_envelope(
        {
            "source": "spiderfoot",
            "version": SPIDERFOOT_VERSION,
            "commit": SPIDERFOOT_COMMIT,
            "status": status,
            "seed": dict(seed),
            "modules_requested": [spec["name"] for spec in MODULES],
            "modules_run": runnable,
            "skipped": skipped,
            "api_keys_injected": injected,
            "events": events,
            "errors": errors,
            "scan_exit_code": exit_code,
            "stderr_tail": stderr[-4000:] if stderr else "",
        }
    )
    # The envelope is the runner contract. A partial SpiderFoot scan is still
    # valid evidence, so the process exits cleanly and the adapter records the
    # partial status from the envelope.
    return 0 if events or status == "ok" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a curated SpiderFoot 4.0 batch for Aletheia."
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="run the offline SpiderFoot help smoke test and exit",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="validate the curated module catalogue and seed parsers without network access",
    )
    parser.add_argument("seed", nargs="?", help="seed as type:value, e.g. domain:example.com")
    args = parser.parse_args(argv)

    if args.health:
        return _run_health()
    if args.selftest:
        errors = []
        runnable, skipped = select_modules(os.environ)
        if len(MODULES) != 14:
            errors.append(f"expected 14 curated modules, got {len(MODULES)}")
        for probe in ("domain:example.com", "ip:8.8.8.8", "email:test@example.com"):
            try:
                parse_seed(probe)
            except SeedError as exc:
                errors.append(f"{probe}: {exc}")
        _write_envelope(
            {
                "status": "ok" if not errors else "failed",
                "modules_requested": [spec["name"] for spec in MODULES],
                "modules_run": runnable,
                "skipped": skipped,
                "errors": errors,
            }
        )
        return 0 if not errors else 1
    if not args.seed:
        parser.error("a seed is required unless --health or --selftest is used")
    try:
        seed = parse_seed(args.seed)
    except SeedError as exc:
        _write_envelope(
            {
                "source": "spiderfoot",
                "version": SPIDERFOOT_VERSION,
                "status": "failed",
                "seed": {"raw": args.seed},
                "modules_run": [],
                "skipped": [],
                "events": [],
                "errors": [str(exc)],
            }
        )
        return 2
    return run_scan(seed)


if __name__ == "__main__":
    raise SystemExit(main())
